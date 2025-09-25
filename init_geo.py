import os
import argparse
import torch
import numpy as np
from pathlib import Path
from time import time

os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
from icecream import ic
ic(torch.cuda.is_available())  # Check if CUDA is available
ic(torch.cuda.device_count())

from mast3r.model import AsymmetricMASt3R
from dust3r.image_pairs import make_pairs
from dust3r.inference import inference
from dust3r.utils.device import to_numpy
from dust3r.utils.geometry import inv
from dust3r.cloud_opt import global_aligner, GlobalAlignerMode
from utils.sfm_utils import (save_intrinsics, save_extrinsic, save_points3D, save_time, save_images_and_masks,
                             init_filestructure, get_sorted_image_files, split_train_test, load_images, compute_co_vis_masks)
from utils.camera_utils import generate_interpolated_path


def main(source_path, model_path, ckpt_path, device, batch_size, image_size, schedule, lr, niter, 
         min_conf_thr, llffhold, n_views, co_vis_dsp, depth_thre, conf_aware_ranking=False, focal_avg=False, infer_video=False):

    # ---------------- (1) Load model and images ----------------  
    save_path, sparse_0_path, sparse_1_path = init_filestructure(Path(source_path), n_views)
    model = AsymmetricMASt3R.from_pretrained(ckpt_path).to(device)
    image_dir = Path(source_path) / 'images'
    image_files, image_suffix = get_sorted_image_files(image_dir)
    if infer_video:
        train_img_files = image_files
    else:
        train_img_files, test_img_files = split_train_test(image_files, llffhold, n_views, verbose=True)
    
    # when geometry init, only use train images
    image_files = train_img_files
    images, org_imgs_shape = load_images(image_files, size=image_size)

    start_time = time()
    print(f'>> Making pairs...')
    pairs = make_pairs(images, scene_graph='complete', prefilter=None, symmetrize=True)
    print(f'>> Inference...')
    output = inference(pairs, model, device, batch_size=1, verbose=True)
    print(f'>> Global alignment...')
    scene = global_aligner(output, device=device, mode=GlobalAlignerMode.PointCloudOptimizer)
    loss = scene.compute_global_alignment(init="mst", niter=300, schedule=schedule, lr=lr, focal_avg=focal_avg)

    # Extract scene information
    extrinsics_w2c = inv(to_numpy(scene.get_im_poses()))
    intrinsics = to_numpy(scene.get_intrinsics())
    focals = to_numpy(scene.get_focals())
    imgs = np.array(scene.imgs)
    pts3d = to_numpy(scene.get_pts3d())
    pts3d = np.array(pts3d)
    depthmaps = to_numpy(scene.im_depthmaps.detach().cpu().numpy())
    values = [param.detach().cpu().numpy() for param in scene.im_conf]
    confs = np.array(values)
    
    if conf_aware_ranking:
        print(f'>> Confiden-aware Ranking...')
        avg_conf_scores = confs.mean(axis=(1, 2))
        sorted_conf_indices = np.argsort(avg_conf_scores)[::-1]
        sorted_conf_avg_conf_scores = avg_conf_scores[sorted_conf_indices]
        print("Sorted indices:", sorted_conf_indices)
        print("Sorted average confidence scores:", sorted_conf_avg_conf_scores)
    else:
        sorted_conf_indices = np.arange(n_views)
        print("Sorted indices:", sorted_conf_indices)

    # Calculate the co-visibility mask
    print(f'>> Calculate the co-visibility mask...')
    if depth_thre > 0:
        overlapping_masks = compute_co_vis_masks(sorted_conf_indices, depthmaps, pts3d, intrinsics, extrinsics_w2c, imgs.shape, depth_threshold=depth_thre)
        overlapping_masks = ~overlapping_masks
    else:
        co_vis_dsp = False
        overlapping_masks = None
    
    # Read segmentation masks from PNG alpha channel and combine with existing masks
    print(f'>> Reading segmentation masks from PNG alpha channel...')
    segmentation_masks = []
    for img_file in image_files:
        # Load PNG image with alpha channel
        import cv2
        img_rgba = cv2.imread(str(img_file), cv2.IMREAD_UNCHANGED)
        if img_rgba.shape[2] == 4:  # Has alpha channel
            # Extract alpha channel as mask (0-255 -> 0-1)
            alpha_mask = img_rgba[:, :, 3] / 255.0
            # Resize mask to match processed image size
            alpha_mask_resized = cv2.resize(alpha_mask, (imgs.shape[2], imgs.shape[1]))
            segmentation_masks.append(alpha_mask_resized)
        else:
            # If no alpha channel, create a mask of all ones (no masking)
            segmentation_masks.append(np.ones(( imgs.shape[1],imgs.shape[2])))
    
    # Convert to numpy array
    segmentation_masks = np.array(segmentation_masks)
    # Invert masks: 1 for background (to be ignored), 0 for foreground (to be kept)
    alpha_masks = segmentation_masks
    print(f'>> Loaded {len(segmentation_masks)} segmentation masks from PNG alpha channel')
    
    # Combine with existing overlapping_masks (take intersection)
    if overlapping_masks is not None:
        # Take intersection: both masks should indicate pixels to ignore
        overlapping_masks = np.logical_and(overlapping_masks, alpha_masks)
        print(f'>> Combined co-visibility masks with alpha channel masks')
    else:
        # If no co-visibility masks, use only alpha masks
        overlapping_masks = alpha_masks
        print(f'>> Using only alpha channel masks (no co-visibility masks)')
    end_time = time()
    Train_Time = end_time - start_time
    print(f"Time taken for {n_views} views: {Train_Time} seconds")
    save_time(model_path, '[1] coarse_init_TrainTime', Train_Time)

    # ---------------- (2) Interpolate training pose to get initial testing pose ----------------
    if not infer_video:
        n_train = len(train_img_files)
        n_test = len(test_img_files)

        if n_train < n_test:
            n_interp = (n_test // (n_train-1)) + 1
            all_inter_pose = []
            for i in range(n_train-1):
                tmp_inter_pose = generate_interpolated_path(poses=extrinsics_w2c[i:i+2], n_interp=n_interp)
                all_inter_pose.append(tmp_inter_pose)
            all_inter_pose = np.concatenate(all_inter_pose, axis=0)
            all_inter_pose = np.concatenate([all_inter_pose, extrinsics_w2c[-1][:3, :].reshape(1, 3, 4)], axis=0)
            indices = np.linspace(0, all_inter_pose.shape[0] - 1, n_test, dtype=int)
            sampled_poses = all_inter_pose[indices]
            sampled_poses = np.array(sampled_poses).reshape(-1, 3, 4)
            assert sampled_poses.shape[0] == n_test
            inter_pose_list = []
            for p in sampled_poses:
                tmp_view = np.eye(4)
                tmp_view[:3, :3] = p[:3, :3]
                tmp_view[:3, 3] = p[:3, 3]
                inter_pose_list.append(tmp_view)
            pose_test_init = np.stack(inter_pose_list, 0)
        else:
            indices = np.linspace(0, extrinsics_w2c.shape[0] - 1, n_test, dtype=int)
            pose_test_init = extrinsics_w2c[indices]

        save_extrinsic(sparse_1_path, pose_test_init, test_img_files, image_suffix)
        test_focals = np.repeat(focals[0], n_test)
        save_intrinsics(sparse_1_path, test_focals, org_imgs_shape, imgs.shape, save_focals=False)
    # -----------------------------------------------------------------------------------------

    # Save results
    focals = np.repeat(focals[0], n_views)
    print(f'>> Saving results...')
    end_time = time()
    save_time(model_path, '[1] init_geo', end_time - start_time)
    save_extrinsic(sparse_0_path, extrinsics_w2c, image_files, image_suffix)
    save_intrinsics(sparse_0_path, focals, org_imgs_shape, imgs.shape, save_focals=True)
    pts_num = save_points3D(sparse_0_path, imgs, pts3d, confs.reshape(pts3d.shape[0], -1), overlapping_masks, use_masks=co_vis_dsp, save_all_pts=True, save_txt_path=model_path, depth_threshold=depth_thre)
    save_images_and_masks(sparse_0_path, n_views, imgs, overlapping_masks, image_files, image_suffix)
    print(f'[INFO] MASt3R Reconstruction is successfully converted to COLMAP files in: {str(sparse_0_path)}')
    print(f'[INFO] Number of points: {pts3d.reshape(-1, 3).shape[0]}')    
    print(f'[INFO] Number of points after downsampling: {pts_num}')

if __name__ == "__main__":
    # 测试代码 - 使用Test_data/Image目录中的图像
    import sys
    if len(sys.argv) == 1:  # 如果没有命令行参数，运行测试
        print("=" * 60)
        print("运行测试模式 - 使用Test_data/Image目录中的图像")
        print("=" * 60)
        
        # 测试参数配置（与reconstruction_processor.py一致）
        test_source_path = "/home/livablecity/InstantSplat/Test_data"
        test_model_path = "/home/livablecity/InstantSplat/test_output"
        test_ckpt_path = './mast3r/checkpoints/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric.pth'
        test_device = 'cuda'
        test_batch_size = 1
        test_image_size = 512
        test_schedule = 'cosine'
        test_lr = 0.01
        test_niter = 300
        test_min_conf_thr = 5
        test_llffhold = 8
        test_n_views = 12
        test_co_vis_dsp = True
        test_depth_thre = 0.01
        test_conf_aware_ranking = True
        test_focal_avg = True
        test_infer_video = True
        
        # 创建输出目录
        os.makedirs(test_model_path, exist_ok=True)
        
        print(f"源路径: {test_source_path}")
        print(f"输出路径: {test_model_path}")
        print(f"视图数量: {test_n_views}")
        print(f"使用CUDA: {test_device}")
        print(f"共视掩码: {test_co_vis_dsp}")
        print(f"深度阈值: {test_depth_thre}")
        print("-" * 60)
        
        # 运行测试
        try:
            main(
                source_path=test_source_path,
                model_path=test_model_path,
                ckpt_path=test_ckpt_path,
                device=test_device,
                batch_size=test_batch_size,
                image_size=test_image_size,
                schedule=test_schedule,
                lr=test_lr,
                niter=test_niter,
                min_conf_thr=test_min_conf_thr,
                llffhold=test_llffhold,
                n_views=test_n_views,
                co_vis_dsp=test_co_vis_dsp,
                depth_thre=test_depth_thre,
                conf_aware_ranking=test_conf_aware_ranking,
                focal_avg=test_focal_avg,
                infer_video=test_infer_video
            )
            print("=" * 60)
            print("测试完成！结果保存在:", test_model_path)
            print("=" * 60)
        except Exception as e:
            print("=" * 60)
            print(f"测试失败: {str(e)}")
            print("=" * 60)
            raise
    else:
        # 正常的命令行参数解析模式
        parser = argparse.ArgumentParser(description='Process images and save results.')
        parser.add_argument('--source_path', '-s', type=str, required=True, help='Directory containing images')
        parser.add_argument('--model_path', '-m', type=str, required=True, help='Directory to save the results')
        parser.add_argument('--ckpt_path', type=str,
            default='./mast3r/checkpoints/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric.pth', help='Path to the model checkpoint')
        parser.add_argument('--device', type=str, default='cuda', help='Device to use for inference')
        parser.add_argument('--batch_size', type=int, default=1, help='Batch size for processing images')
        parser.add_argument('--image_size', type=int, default=512, help='Size to resize images')
        parser.add_argument('--schedule', type=str, default='cosine', help='Learning rate schedule')
        parser.add_argument('--lr', type=float, default=0.01, help='Learning rate')
        parser.add_argument('--niter', type=int, default=300, help='Number of iterations')
        parser.add_argument('--min_conf_thr', type=float, default=5, help='Minimum confidence threshold')
        parser.add_argument('--llffhold', type=int, default=8, help='')
        parser.add_argument('--n_views', type=int, default=3, help='')
        parser.add_argument('--focal_avg', action="store_true")
        parser.add_argument('--conf_aware_ranking', action="store_true")
        parser.add_argument('--co_vis_dsp', action="store_true")
        parser.add_argument('--depth_thre', type=float, default=0.01, help='Depth threshold')
        parser.add_argument('--infer_video', action="store_true")

        args = parser.parse_args()
        main(args.source_path, args.model_path, args.ckpt_path, args.device, args.batch_size, args.image_size, args.schedule, args.lr, args.niter,         
              args.min_conf_thr, args.llffhold, args.n_views, args.co_vis_dsp, args.depth_thre, args.conf_aware_ranking, args.focal_avg, args.infer_video)

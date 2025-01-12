import pickle
import time

import numpy as np
import torch
import tqdm
import copy

from pcdet.models import load_data_to_gpu
from pcdet.utils import common_utils


def statistics_info(cfg, ret_dict, metric, disp_dict):
    for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
        metric['recall_roi_%s' % str(cur_thresh)] += ret_dict.get('roi_%s' % str(cur_thresh), 0)
        metric['recall_rcnn_%s' % str(cur_thresh)] += ret_dict.get('rcnn_%s' % str(cur_thresh), 0)
        metric['recall_roi_%s_car' % str(cur_thresh)] += ret_dict.get('roi_%s_car' % str(cur_thresh), 0)
        metric['recall_rcnn_%s_car' % str(cur_thresh)] += ret_dict.get('rcnn_%s_car' % str(cur_thresh), 0)
        metric['recall_roi_%s_ped' % str(cur_thresh)] += ret_dict.get('roi_%s_ped' % str(cur_thresh), 0)
        metric['recall_rcnn_%s_ped' % str(cur_thresh)] += ret_dict.get('rcnn_%s_ped' % str(cur_thresh), 0)
        metric['recall_roi_%s_cyc' % str(cur_thresh)] += ret_dict.get('roi_%s_cyc' % str(cur_thresh), 0)
        metric['recall_rcnn_%s_cyc' % str(cur_thresh)] += ret_dict.get('rcnn_%s_cyc' % str(cur_thresh), 0)

    metric['gt_num'] += ret_dict.get('gt', 0)
    metric['gt_car_num'] += ret_dict.get('gt_car', 0)
    metric['gt_ped_num'] += ret_dict.get('gt_ped', 0)
    metric['gt_cyc_num'] += ret_dict.get('gt_cyc', 0)
    min_thresh = cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST[0]
    disp_dict['recall_%s' % str(min_thresh)] = \
        '(%d, %d) / %d' % (metric['recall_roi_%s' % str(min_thresh)], metric['recall_rcnn_%s' % str(min_thresh)], metric['gt_num'])


def statistics_info_list(cfg, ret_dict_list, metric, disp_dict):
    for i in range(len(ret_dict_list)):
        ret_dict = ret_dict_list[i]
        for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
            metric[i]['recall_roi_%s' % str(cur_thresh)] += ret_dict.get('roi_%s' % str(cur_thresh), 0)
            metric[i]['recall_rcnn_%s' % str(cur_thresh)] += ret_dict.get('rcnn_%s' % str(cur_thresh), 0)
            metric[i]['recall_roi_%s_car' % str(cur_thresh)] += ret_dict.get('roi_%s_car' % str(cur_thresh), 0)
            metric[i]['recall_rcnn_%s_car' % str(cur_thresh)] += ret_dict.get('rcnn_%s_car' % str(cur_thresh), 0)
            metric[i]['recall_roi_%s_ped' % str(cur_thresh)] += ret_dict.get('roi_%s_ped' % str(cur_thresh), 0)
            metric[i]['recall_rcnn_%s_ped' % str(cur_thresh)] += ret_dict.get('rcnn_%s_ped' % str(cur_thresh), 0)
            metric[i]['recall_roi_%s_cyc' % str(cur_thresh)] += ret_dict.get('roi_%s_cyc' % str(cur_thresh), 0)
            metric[i]['recall_rcnn_%s_cyc' % str(cur_thresh)] += ret_dict.get('rcnn_%s_cyc' % str(cur_thresh), 0)

        metric[i]['gt_num'] += ret_dict.get('gt', 0)
        metric[i]['gt_car_num'] += ret_dict.get('gt_car', 0)
        metric[i]['gt_ped_num'] += ret_dict.get('gt_ped', 0)
        metric[i]['gt_cyc_num'] += ret_dict.get('gt_cyc', 0)

        min_thresh = cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST[0]
        disp_dict['recall_%s' % str(min_thresh)] = \
            '(%d, %d) / %d' % (metric[i]['recall_roi_%s' % str(min_thresh)], metric[i]['recall_rcnn_%s' % str(min_thresh)], metric[i]['gt_num'])


def eval_one_epoch(cfg, model, dataloader, epoch_id, logger, dist_test=False, save_to_file=False, result_dir=None, unitest=False, eval_by_range=False):
    result_dir.mkdir(parents=True, exist_ok=True)

    final_output_dir = result_dir / 'final_result' / 'data'
    if save_to_file:
        final_output_dir.mkdir(parents=True, exist_ok=True)

    metric = {
        'gt_num': 0,
        'gt_car_num': 0,
        'gt_ped_num': 0,
        'gt_cyc_num': 0
    }
    for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
        metric['recall_roi_%s' % str(cur_thresh)] = 0
        metric['recall_rcnn_%s' % str(cur_thresh)] = 0
        metric['recall_roi_%s_car' % str(cur_thresh)] = 0
        metric['recall_rcnn_%s_car' % str(cur_thresh)] = 0
        metric['recall_roi_%s_ped' % str(cur_thresh)] = 0
        metric['recall_rcnn_%s_ped' % str(cur_thresh)] = 0
        metric['recall_roi_%s_cyc' % str(cur_thresh)] = 0
        metric['recall_rcnn_%s_cyc' % str(cur_thresh)] = 0

    metric_list = []
    for i in range(4):
        metric_list.append(copy.deepcopy(metric))

    dataset = dataloader.dataset
    class_names = dataset.class_names
    det_annos = []

    logger.info('*************** EPOCH %s EVALUATION *****************' % epoch_id)
    if dist_test:
        num_gpus = torch.cuda.device_count()
        local_rank = cfg.LOCAL_RANK % num_gpus
        model = torch.nn.parallel.DistributedDataParallel(
                model,
                device_ids=[local_rank],
                broadcast_buffers=False
        )
    model.eval()

    if cfg.LOCAL_RANK == 0:
        progress_bar = tqdm.tqdm(total=len(dataloader), leave=True, desc='eval', dynamic_ncols=True)
    start_time = time.time()

    det_annos_list = [[] for i in range(4)]

    for i, batch_dict in enumerate(dataloader):
        load_data_to_gpu(batch_dict)
        with torch.no_grad():
            pred_dicts_list, ret_dict = model(batch_dict)
        disp_dict = {}

        if eval_by_range:
            statistics_info_list(cfg, ret_dict, metric_list, disp_dict)
        else:
            statistics_info(cfg, ret_dict[0], metric, disp_dict)
        annos_list = []

        for j, pred_dicts in enumerate(pred_dicts_list):
            annos = dataset.generate_prediction_dicts(
                batch_dict, pred_dicts, class_names,
                output_path=final_output_dir if save_to_file else None
            )
            annos_list.append(annos)

            det_annos_list[j] += annos
        if cfg.LOCAL_RANK == 0:
            progress_bar.set_postfix(disp_dict)
            progress_bar.update()
        if unitest and i > 8:
            break

    if cfg.LOCAL_RANK == 0:
        progress_bar.close()

    if dist_test:
        rank, world_size = common_utils.get_dist_info()
        for i in range(len(det_annos_list)):
            det_annos_list[i] = common_utils.merge_results_dist(det_annos_list[i], len(dataset), tmpdir=result_dir / 'tmpdir')
            if eval_by_range:
                metric_list[i] = common_utils.merge_results_dist([metric_list[i]], world_size, tmpdir=result_dir / 'tmpdir')
        if not eval_by_range:
            metric = common_utils.merge_results_dist([metric], world_size, tmpdir=result_dir / 'tmpdir')

    logger.info('*************** Performance of EPOCH %s *****************' % epoch_id)
    sec_per_example = (time.time() - start_time) / len(dataloader.dataset)
    logger.info('Generate label finished(sec_per_example: %.4f second).' % sec_per_example)

    if cfg.LOCAL_RANK != 0:
        return {}

    ret_dict = {}
    if dist_test:
        if not eval_by_range:
            for key, val in metric[0].items():
                for k in range(1, world_size):
                    metric[0][key] += metric[k][key]
            metric = metric[0]
        else:
            for i, metric in enumerate(metric_list):
                for key, val in metric[0].items():
                    for k in range(1, world_size):
                        metric[0][key] += metric[k][key]
                metric_list[i] = metric[0]
    
    if eval_by_range:
        Range = ["All", "Near", "Mid", "Far"]
        for i in range(len(metric_list)):
            metric = metric_list[i]
            gt_num_cnt = metric['gt_num']
            logger.info(Range[i])

            logger.info('All')
            for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
                cur_roi_recall = metric['recall_roi_%s' % str(cur_thresh)] / max(gt_num_cnt, 1)
                cur_rcnn_recall = metric['recall_rcnn_%s' % str(cur_thresh)] / max(gt_num_cnt, 1)
                logger.info('recall_roi_%s: %f' % (cur_thresh, cur_roi_recall))
                logger.info('recall_rcnn_%s: %f' % (cur_thresh, cur_rcnn_recall))
                ret_dict['recall/roi_%s' % str(cur_thresh)] = cur_roi_recall
                ret_dict['recall/rcnn_%s' % str(cur_thresh)] = cur_rcnn_recall
            
            logger.info('Car')
            gt_num_cnt = metric['gt_car_num']
            for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
                cur_roi_recall = metric['recall_roi_%s_car' % str(cur_thresh)] / max(gt_num_cnt, 1)
                cur_rcnn_recall = metric['recall_rcnn_%s_car' % str(cur_thresh)] / max(gt_num_cnt, 1)
                logger.info('recall_roi_%s_car: %f' % (cur_thresh, cur_roi_recall))
                logger.info('recall_rcnn_%s_car: %f' % (cur_thresh, cur_rcnn_recall))
            
            logger.info('Ped')
            gt_num_cnt = metric['gt_ped_num']
            for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
                cur_roi_recall = metric['recall_roi_%s_ped' % str(cur_thresh)] / max(gt_num_cnt, 1)
                cur_rcnn_recall = metric['recall_rcnn_%s_ped' % str(cur_thresh)] / max(gt_num_cnt, 1)
                logger.info('recall_roi_%s_ped: %f' % (cur_thresh, cur_roi_recall))
                logger.info('recall_rcnn_%s_ped: %f' % (cur_thresh, cur_rcnn_recall))
            
            logger.info('Cyc')
            gt_num_cnt = metric['gt_cyc_num']
            for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
                cur_roi_recall = metric['recall_roi_%s_cyc' % str(cur_thresh)] / max(gt_num_cnt, 1)
                cur_rcnn_recall = metric['recall_rcnn_%s_cyc' % str(cur_thresh)] / max(gt_num_cnt, 1)
                logger.info('recall_roi_%s_cyc: %f' % (cur_thresh, cur_roi_recall))
                logger.info('recall_rcnn_%s_cyc: %f' % (cur_thresh, cur_rcnn_recall))


        with open(result_dir / 'result.pkl', 'wb') as f:
            pickle.dump(det_annos, f)
        
        
        for det_annos in det_annos_list:
            total_pred_objects = 0
            for anno in det_annos:
                total_pred_objects += anno['name'].__len__()
            logger.info('Average predicted number of objects(%d samples): %.3f'
                        % (len(det_annos), total_pred_objects / max(1, len(det_annos))))

            result_str, result_dict = dataset.evaluation(
                det_annos, class_names,
                eval_metric=cfg.MODEL.POST_PROCESSING.EVAL_METRIC,
                output_path=final_output_dir
            )

            logger.info(result_str)
            ret_dict.update(result_dict)
    else:
        gt_num_cnt = metric['gt_num']

        logger.info('All')
        for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
            cur_roi_recall = metric['recall_roi_%s' % str(cur_thresh)] / max(gt_num_cnt, 1)
            cur_rcnn_recall = metric['recall_rcnn_%s' % str(cur_thresh)] / max(gt_num_cnt, 1)
            logger.info('recall_roi_%s: %f' % (cur_thresh, cur_roi_recall))
            logger.info('recall_rcnn_%s: %f' % (cur_thresh, cur_rcnn_recall))
            ret_dict['recall/roi_%s' % str(cur_thresh)] = cur_roi_recall
            ret_dict['recall/rcnn_%s' % str(cur_thresh)] = cur_rcnn_recall
        
        logger.info('Car')
        gt_num_cnt = metric['gt_car_num']
        for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
            cur_roi_recall = metric['recall_roi_%s_car' % str(cur_thresh)] / max(gt_num_cnt, 1)
            cur_rcnn_recall = metric['recall_rcnn_%s_car' % str(cur_thresh)] / max(gt_num_cnt, 1)
            logger.info('recall_roi_%s_car: %f' % (cur_thresh, cur_roi_recall))
            logger.info('recall_rcnn_%s_car: %f' % (cur_thresh, cur_rcnn_recall))
        
        logger.info('Ped')
        gt_num_cnt = metric['gt_ped_num']
        for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
            cur_roi_recall = metric['recall_roi_%s_ped' % str(cur_thresh)] / max(gt_num_cnt, 1)
            cur_rcnn_recall = metric['recall_rcnn_%s_ped' % str(cur_thresh)] / max(gt_num_cnt, 1)
            logger.info('recall_roi_%s_ped: %f' % (cur_thresh, cur_roi_recall))
            logger.info('recall_rcnn_%s_ped: %f' % (cur_thresh, cur_rcnn_recall))
        
        logger.info('Cyc')
        gt_num_cnt = metric['gt_cyc_num']
        for cur_thresh in cfg.MODEL.POST_PROCESSING.RECALL_THRESH_LIST:
            cur_roi_recall = metric['recall_roi_%s_cyc' % str(cur_thresh)] / max(gt_num_cnt, 1)
            cur_rcnn_recall = metric['recall_rcnn_%s_cyc' % str(cur_thresh)] / max(gt_num_cnt, 1)
            logger.info('recall_roi_%s_cyc: %f' % (cur_thresh, cur_roi_recall))
            logger.info('recall_rcnn_%s_cyc: %f' % (cur_thresh, cur_rcnn_recall))

        with open(result_dir / 'result.pkl', 'wb') as f:
           pickle.dump(det_annos, f)

        total_pred_objects = 0
        for anno in det_annos:
            total_pred_objects += anno['name'].__len__()
        logger.info('Average predicted number of objects(%d samples): %.3f'
                    % (len(det_annos), total_pred_objects / max(1, len(det_annos))))

        det_annos = det_annos_list[0]
        result_str, result_dict = dataset.evaluation(
            det_annos, class_names,
            eval_metric=cfg.MODEL.POST_PROCESSING.EVAL_METRIC,
            output_path=final_output_dir
        )

        logger.info(result_str)
        ret_dict.update(result_dict)


    logger.info('Result is save to %s' % result_dir)
    logger.info('****************Evaluation done.*****************')
    return ret_dict


if __name__ == '__main__':
    pass

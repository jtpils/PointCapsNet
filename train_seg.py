import argparse
import os
import torch
import torch.nn.parallel
import torch.optim as optim
import torch.utils.data
from collections import defaultdict
from torch.autograd import Variable
from DataLoader import PartDataset
from PointCapsNetSeg import PointNetSeg
import torch.nn.functional as F
import datetime
import logging
from DataLoader import load_segdata
from pathlib import Path
from utils import test_seg
from tqdm import tqdm

def parse_args():
    parser = argparse.ArgumentParser('PointCapsNetSeg')
    parser.add_argument('--batchSize', type=int, default=32, help='input batch size')
    parser.add_argument('--workers', type=int, default=4, help='number of data loading workers')
    parser.add_argument('--epoch', type=int, default=25, help='number of epochs to train for')
    parser.add_argument('--data_path', type=str, default='./data/shapenet16/', help='data path')
    parser.add_argument('--result_dir', type=str, default='./experiment/results/',help='dir to save pictures')
    parser.add_argument('--log_dir', type=str, default='./experiment/logs/',help='decay rate of learning rate')
    parser.add_argument('--pretrain', type=str, default=None,help='whether use pretrain model')
    parser.add_argument('--train_metric', type=str, default=False, help='Whether evaluate on training data')
    parser.add_argument('--gpu', type=str, default='0', help='specify gpu device')

    return parser.parse_args()

def main(args):
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
    '''CREATE DIR'''
    experiment_dir = Path('./experiment/')
    experiment_dir.mkdir(exist_ok=True)
    result_dir = Path(args.result_dir)
    result_dir.mkdir(exist_ok=True)
    checkpoints_dir = Path('./experiment/checkpoints/')
    checkpoints_dir.mkdir(exist_ok=True)
    log_dir = Path(args.log_dir)
    log_dir.mkdir(exist_ok=True)

    '''LOG'''
    args = parse_args()
    logger = logging.getLogger("PointCapsNetSeg")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(args.log_dir + 'train-'+ str(datetime.datetime.now().strftime('%Y-%m-%d %H-%M'))+'.txt')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info('---------------------------------------------------TRANING---------------------------------------------------')
    logger.info('PARAMETER ...')
    logger.info(args)
    DATA_PATH = args.data_path
    train_data, train_label, test_data, test_label = load_segdata(DATA_PATH)
    logger.info("The number of training data is: %d",train_data.shape[0])
    logger.info("The number of test data is: %d", test_data.shape[0])

    dataset = PartDataset(train_data,train_label)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=args.batchSize,
                                             shuffle=True, num_workers=int(args.workers))

    test_dataset = PartDataset(test_data,test_label)
    testdataloader = torch.utils.data.DataLoader(test_dataset, batch_size=args.batchSize,
                                                 shuffle=True, num_workers=int(args.workers))

    num_classes = 50
    blue = lambda x: '\033[94m' + x + '\033[0m'

    model = PointNetSeg(k=num_classes)
    if args.pretrain is not None:
        model.load_state_dict(torch.load(args.pretrain))

    optimizer = optim.SGD(model.parameters(), lr=0.01, momentum=0.9)
    model.cuda()
    history = defaultdict(lambda: list())
    best_acc = 0
    COMPUTE_TRAIN_METRICS = args.train_metric

    for epoch in range(args.epoch):
        for i, data in tqdm(enumerate(dataloader, 0),total=len(dataloader),smoothing=0.9):
            points, target = data
            points, target = Variable(points), Variable(target.long())
            points = points.transpose(2, 1)
            points, target = points.cuda(), target.cuda()
            optimizer.zero_grad()
            model = model.train()
            pred, _ = model(points)
            pred = pred.view(-1, num_classes)
            target = target.view(-1, 1)[:, 0]
            loss = F.nll_loss(pred, target)
            history['loss'].append(loss.cpu().data.numpy())
            loss.backward()
            optimizer.step()
        if COMPUTE_TRAIN_METRICS:
            train_metrics, train_hist_acc = test_seg(model, dataloader)
            print('Epoch %d  %s loss: %f accuracy: %f' % (
                epoch, blue('train'), history['loss'][-1], train_metrics))
            logger.info('Epoch %d  %s loss: %f accuracy: %f' % (
                epoch, blue('train'), history['loss'][-1], train_metrics))


        test_metrics, test_hist_acc = test_seg(model, testdataloader)

        print('Epoch %d  %s accuracy: %f' % (
                 epoch, blue('test'), test_metrics))
        logger.info('Epoch %d  %s accuracy: %f' % (
                 epoch, blue('test'), test_metrics))
        if test_metrics > best_acc:
            best_acc = test_metrics
            torch.save(model.state_dict(), '%s/seg_model_%d_%.4f.pth' % (checkpoints_dir, epoch, best_acc))
            logger.info('Save model..')
            print('Save model..')


if __name__ == '__main__':
    args = parse_args()
    main(args)


from torchvision import datasets, transforms
from torch.utils.data import Subset, DataLoader
import numpy as np
import os

# for fixing RuntimeError: received 0 items of ancdata
import torch.multiprocessing
torch.multiprocessing.set_sharing_strategy('file_system')


def split(dataset, val_ratio, seed):
    train_cnt = int((1 - val_ratio) * len(dataset))
    np.random.seed(seed)
    perm = np.random.permutation(len(dataset))
    train_indices = perm[:train_cnt]
    val_indices = perm[train_cnt:]
    train_data = Subset(dataset, train_indices)
    val_data = Subset(dataset, val_indices)
    return train_data, val_data


def load_mnist_datasets(val_ratio=0.2, noise_level=0.0, seed=42):
    data_dir = os.path.join(os.path.dirname(__file__), '../data/mnist/')

    train_data = datasets.MNIST(data_dir, download=True, train=True, transform=transforms.ToTensor())
    test_data = datasets.MNIST(data_dir, download=True, train=False, transform=transforms.ToTensor())
    train_data, val_data = split(train_data, val_ratio, seed)

    train_data.dataset_name = 'mnist'
    val_data.dataset_name = 'mnist'
    test_data.dataset_name = 'mnist'

    # corrupt noise_level percent of the training labels
    is_corrupted = np.zeros(len(train_data), dtype=int)  # 0 clean, 1 corrupted, 2 accidentally correct
    for current_idx, sample_idx in enumerate(train_data.indices):
        if np.random.uniform(0, 1) < noise_level:
            new_label = np.random.randint(10)
            if new_label == train_data.dataset.targets[sample_idx]:
                is_corrupted[current_idx] = 2
            else:
                is_corrupted[current_idx] = 1
            train_data.dataset.targets[sample_idx] = new_label

    return train_data, val_data, test_data, is_corrupted


def load_mnist_loaders(val_ratio=0.2, batch_size=128, noise_level=0.0, seed=42, drop_last=False,
                       num_train_examples=None):
    train_data, val_data, test_data, _ = load_mnist_datasets(val_ratio=val_ratio,
                                                             noise_level=noise_level, seed=seed)

    if num_train_examples is not None:
        subset = np.random.choice(len(train_data), num_train_examples, replace=False)
        train_data = Subset(train_data, subset)

    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True,
                              num_workers=4, drop_last=drop_last)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=True,
                            num_workers=4, drop_last=drop_last)
    test_loader = DataLoader(test_data, batch_size=batch_size, shuffle=True,
                             num_workers=4, drop_last=drop_last)

    return train_loader, val_loader, test_loader


def load_cifar10_datasets(val_ratio=0.2, noise_level=0.0, seed=42):
    data_dir = os.path.join(os.path.dirname(__file__), '../data/cifar10/')

    train_data = datasets.CIFAR10(data_dir, download=True, train=True, transform=transforms.ToTensor())
    test_data = datasets.CIFAR10(data_dir, download=True, train=False, transform=transforms.ToTensor())
    train_data, val_data = split(train_data, val_ratio, seed)

    train_data.dataset_name = 'cifar10'
    val_data.dataset_name = 'cifar10'
    test_data.dataset_name = 'cifar10'

    # corrupt noise_level percent of the training labels
    is_corrupted = np.zeros(len(train_data), dtype=int)  # 0 clean, 1 corrupted, 2 accidentally correct
    for current_idx, sample_idx in enumerate(train_data.indices):
        if np.random.uniform(0, 1) < noise_level:
            new_label = np.random.randint(10)
            if new_label == train_data.dataset.targets[sample_idx]:
                is_corrupted[current_idx] = 2
            else:
                is_corrupted[current_idx] = 1
            train_data.dataset.targets[sample_idx] = new_label

    return train_data, val_data, test_data, is_corrupted


def load_cifar10_loaders(val_ratio=0.2, batch_size=128, noise_level=0.0, seed=42, drop_last=False,
                         num_train_examples=None):
    train_data, val_data, test_data, _ = load_cifar10_datasets(val_ratio=val_ratio,
                                                               noise_level=noise_level, seed=seed)

    if num_train_examples is not None:
        subset = np.random.choice(len(train_data), num_train_examples, replace=False)
        train_data = Subset(train_data, subset)

    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True,
                              num_workers=4, drop_last=drop_last)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=True,
                            num_workers=4, drop_last=drop_last)
    test_loader = DataLoader(test_data, batch_size=batch_size, shuffle=True,
                             num_workers=4, drop_last=drop_last)

    return train_loader, val_loader, test_loader

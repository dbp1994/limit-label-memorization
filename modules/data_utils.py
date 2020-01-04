from torchvision import datasets, transforms
from torch.utils.data import Subset, DataLoader, Dataset
from PIL import Image
import numpy as np
import os

# for fixing RuntimeError: received 0 items of ancdata
import torch.multiprocessing
torch.multiprocessing.set_sharing_strategy('file_system')


def split(n_samples, val_ratio, seed):
    train_cnt = int((1 - val_ratio) * n_samples)
    np.random.seed(seed)
    perm = np.random.permutation(n_samples)
    train_indices = perm[:train_cnt]
    val_indices = perm[train_cnt:]
    return train_indices, val_indices


def uniform_flip_confusion_matrix(n_classes, error_prob):
    cf = error_prob / n_classes * np.ones((n_classes, n_classes))
    cf += (1.0 - error_prob) * np.eye(n_classes)
    assert np.allclose(cf.sum(axis=1), 1)
    return cf


def uniform_error_confusion_matrix(n_classes, error_prob):
    cf = error_prob / (n_classes - 1) * np.ones((n_classes, n_classes))
    for i in range(n_classes):
        cf[i, i] = 1 - error_prob
    assert np.allclose(cf.sum(axis=1), 1)
    return cf


def cifar10_custom_confusion_matrix(n_classes, error_prob):
    assert n_classes == 10
    cf = np.eye(n_classes)
    cf[9][1] = error_prob
    cf[9][9] = 1 - error_prob
    cf[2][0] = error_prob
    cf[2][2] = 1 - error_prob
    cf[4][7] = error_prob
    cf[4][4] = 1 - error_prob
    cf[3][5] = error_prob
    cf[3][3] = 1 - error_prob
    assert np.allclose(cf.sum(axis=1), 1)
    return cf


def remove_random_chunks(x, prob):
    """ Divide the image into 4x4 patches and remove patches randomly.
    """
    ret = x.clone()
    chunk_size = 4
    assert x.shape[0] % chunk_size == 0
    assert x.shape[1] % chunk_size == 0
    n_x_blocks = x.shape[0] // chunk_size
    n_y_blocks = x.shape[1] // chunk_size
    random_value = np.random.uniform(size=(n_x_blocks, n_y_blocks))
    for i in range(n_x_blocks):
        for j in range(n_y_blocks):
            if random_value[i, j] < prob:
                ret[i * chunk_size:(i+1) * chunk_size, j * chunk_size:(j+1) * chunk_size] = 0
    return ret


def create_remove_random_chunks_function(prob=0.5):
    """ Returns a remove_random_chunks function with given probability.
    """
    def modify(x):
        return remove_random_chunks(x, prob=prob)
    return modify


def revert_normalization(samples, dataset):
    means, stds = dataset.statistics
    means = means.to(samples.device)
    stds = stds.to(samples.device)
    if len(samples.shape) == 3:
        samples = samples.unsqueeze(dim=0)
    return (samples * stds.unsqueeze(dim=0).unsqueeze(dim=2).unsqueeze(dim=3) +
            means.unsqueeze(dim=0).unsqueeze(dim=2).unsqueeze(dim=3))


def load_mnist_datasets(val_ratio=0.2, noise_level=0.0, transform_function=None,
                        transform_validation=False, num_train_examples=None, seed=42):
    data_dir = os.path.join(os.path.dirname(__file__), '../data/mnist/')

    # Add normalization. This is done so that models pretrained on ImageNet work well.
    means = torch.tensor([0.456])
    stds = torch.tensor([0.224])
    normalize_transform = transforms.Normalize(mean=means, std=stds)

    composed_transform = transforms.Compose([transforms.ToTensor(), normalize_transform])

    train_val_data = datasets.MNIST(data_dir, download=True, train=True, transform=composed_transform)
    test_data = datasets.MNIST(data_dir, download=True, train=False, transform=composed_transform)

    # split train and validation
    train_indices, val_indices = split(len(train_val_data), val_ratio, seed)
    if num_train_examples is not None:
        train_indices = np.random.choice(train_indices, num_train_examples, replace=False)
    train_data = Subset(train_val_data, train_indices)
    val_data = Subset(train_val_data, val_indices)

    # name datasets and save statistics
    for dataset in [train_data, val_data, test_data]:
        dataset.dataset_name = 'mnist'
        dataset.statistics = (means, stds)

    # corrupt noise_level percent of the training labels
    is_corrupted = np.zeros(len(train_data), dtype=int)  # 0 clean, 1 corrupted, 2 accidentally correct
    for current_idx, sample_idx in enumerate(train_indices):
        if np.random.uniform(0, 1) < noise_level:
            new_label = np.random.randint(10)
            if new_label == train_data.dataset.targets[sample_idx]:
                is_corrupted[current_idx] = 2
            else:
                is_corrupted[current_idx] = 1
            train_data.dataset.targets[sample_idx] = new_label

    # modify images if needed
    if transform_function is not None:
        # transform training samples
        for sample_idx in train_data.indices:
            train_data.dataset.data[sample_idx] = transform_function(train_data.dataset.data[sample_idx])

        if transform_validation:
            # transform validation samples
            for sample_idx in val_data.indices:
                val_data.dataset.data[sample_idx] = transform_function(val_data.dataset.data[sample_idx])

            # transform testing samples
            for sample_idx in range(len(test_data)):
                test_data.data[sample_idx] = transform_function(test_data.data[sample_idx])

    return train_data, val_data, test_data, is_corrupted


def load_mnist_loaders(val_ratio=0.2, batch_size=128, noise_level=0.0, seed=42,
                       drop_last=False, num_train_examples=None, transform_function=None,
                       transform_validation=False):
    train_data, val_data, test_data, _ = load_mnist_datasets(
        val_ratio=val_ratio, noise_level=noise_level, transform_function=transform_function,
        transform_validation=transform_validation, num_train_examples=num_train_examples, seed=seed)

    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True,
                              num_workers=4, drop_last=drop_last)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=True,
                            num_workers=4, drop_last=drop_last)
    test_loader = DataLoader(test_data, batch_size=batch_size, shuffle=True,
                             num_workers=4, drop_last=drop_last)

    return train_loader, val_loader, test_loader


def load_cifar10_datasets(val_ratio=0.2, noise_level=0.0, data_augmentation=False,
                          confusion_function=uniform_flip_confusion_matrix,
                          num_train_examples=None, seed=42):
    data_dir = os.path.join(os.path.dirname(__file__), '../data/cifar10/')

    data_augmentation_transforms = []
    if data_augmentation:
        data_augmentation_transforms = [transforms.RandomHorizontalFlip(),
                                        transforms.RandomCrop(32, 4)]

    # Add normalization. This is done so that models pretrained on ImageNet work well.
    means = torch.tensor([0.485, 0.456, 0.406])
    stds = torch.tensor([0.229, 0.224, 0.225])
    normalize_transform = transforms.Normalize(mean=means, std=stds)
    common_transforms = [transforms.ToTensor(), normalize_transform]

    train_transform = transforms.Compose(data_augmentation_transforms + common_transforms)
    val_transform = transforms.Compose(common_transforms)

    train_data = datasets.CIFAR10(data_dir, download=True, train=True, transform=train_transform)
    val_data = datasets.CIFAR10(data_dir, download=True, train=True, transform=val_transform)
    test_data = datasets.CIFAR10(data_dir, download=True, train=False, transform=val_transform)

    # split train and validation
    train_indices, val_indices = split(len(train_data), val_ratio, seed)
    if num_train_examples is not None:
        train_indices = np.random.choice(train_indices, num_train_examples, replace=False)
    train_data = Subset(train_data, train_indices)
    val_data = Subset(val_data, val_indices)

    # name datasets and save statistics
    for dataset in [train_data, val_data, test_data]:
        dataset.dataset_name = 'cifar10'
        dataset.statistics = (means, stds)

    # corrupt the labels if needed
    is_corrupted = np.zeros(len(train_data), dtype=int)  # 0 clean, 1 corrupted
    cf = confusion_function(n_classes=10, error_prob=noise_level)
    for current_idx, sample_idx in enumerate(train_indices):
        label = train_data.dataset.targets[sample_idx]
        new_label = int(np.random.choice(10, 1, p=np.array(cf[label])))
        train_data.dataset.targets[sample_idx] = new_label
        is_corrupted[current_idx] = (label != new_label)

    return train_data, val_data, test_data, is_corrupted


def load_cifar10_loaders(val_ratio=0.2, batch_size=128, noise_level=0.0, seed=42,
                         drop_last=False, num_train_examples=None, data_augmentation=False,
                         confusion_function=uniform_flip_confusion_matrix):
    train_data, val_data, test_data, _ = load_cifar10_datasets(val_ratio=val_ratio,
                                                               noise_level=noise_level,
                                                               data_augmentation=data_augmentation,
                                                               confusion_function=confusion_function,
                                                               num_train_examples=num_train_examples,
                                                               seed=seed)

    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True,
                              num_workers=4, drop_last=drop_last)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=True,
                            num_workers=4, drop_last=drop_last)
    test_loader = DataLoader(test_data, batch_size=batch_size, shuffle=True,
                             num_workers=4, drop_last=drop_last)

    return train_loader, val_loader, test_loader


class Clothing1M(Dataset):
    def __init__(self, root, img_transform, train=False, valid=False, test=False):
        self.root = root
        if train:
            flist = os.path.join(root, "dmi_annotations/noisy_train.txt")
        if valid:
            flist = os.path.join(root, "dmi_annotations/clean_val.txt")
        if test:
            flist = os.path.join(root, "dmi_annotations/clean_test.txt")

        self.imlist = self.flist_reader(flist)
        self.transform = img_transform
        self.train = train

    def __getitem__(self, index):
        impath, target = self.imlist[index]
        img = Image.open(impath).convert("RGB")
        if self.transform is not None:
            img = self.transform(img)
        return img, target

    def __len__(self):
        return len(self.imlist)

    def flist_reader(self, flist):
        imlist = []
        with open(flist, 'r') as rf:
            for line in rf.readlines():
                row = line.split(" ")
                impath =  self.root + row[0]
                imlabel = row[1]
                imlist.append((impath, int(imlabel)))
        return imlist


def load_clothing1M_datasets(data_augmentation=False, seed=42):
    data_dir = os.path.join(os.path.dirname(__file__), '../data/clothing1M/')

    data_augmentation_transforms = []
    if data_augmentation:
        data_augmentation_transforms = [transforms.RandomCrop(224),
                                        transforms.RandomHorizontalFlip()]

    # Add normalization. This is done so that models pretrained on ImageNet work well.
    means = torch.tensor([0.485, 0.456, 0.406])
    stds = torch.tensor([0.229, 0.224, 0.225])
    normalize_transform = transforms.Normalize(mean=means, std=stds)
    common_transforms = [transforms.ToTensor(), normalize_transform]

    train_transform = transforms.Compose([transforms.Resize((256, 256))] +\
                                         data_augmentation_transforms +\
                                         common_transforms)
    val_transform = transforms.Compose([transforms.Resize((224, 224))] + common_transforms)

    train_data = Clothing1M(root=data_dir, img_transform=train_transform, train=True)
    val_data = Clothing1M(root=data_dir, img_transform=val_transform, valid=True)
    test_data = Clothing1M(root=data_dir, img_transform=val_transform, test=True)

    # name datasets and save statistics
    for dataset in [train_data, val_data, test_data]:
        dataset.dataset_name = 'clothing1M'
        dataset.statistics = (means, stds)

    return train_data, val_data, test_data, None


def load_clothing1M_loaders(batch_size=128, drop_last=False, num_train_examples=None,
                            data_augmentation=False, seed=42):
    train_data, val_data, test_data, _ = load_clothing1M_datasets(data_augmentation=data_augmentation,
                                                                  seed=seed)

    if num_train_examples is not None:
        subset = np.random.choice(len(train_data), num_train_examples, replace=False)
        train_data = Subset(train_data, subset)

    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True,
                              num_workers=32, drop_last=drop_last)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=True,
                            num_workers=32, drop_last=drop_last)
    test_loader = DataLoader(test_data, batch_size=batch_size, shuffle=True,
                             num_workers=32, drop_last=drop_last)

    return train_loader, val_loader, test_loader


def load_data_from_arguments(args):
    """ Helper method for loading data from arguments.
    """
    transform_function = None
    if args.transform_function == 'remove_random_chunks':
        transform_function = create_remove_random_chunks_function(args.remove_prob)

    confusion_function = uniform_flip_confusion_matrix
    if args.label_noise_type == 'error':
        confusion_function = uniform_error_confusion_matrix
    if args.label_noise_type == 'cifar10_custom':
        confusion_function = cifar10_custom_confusion_matrix

    if args.dataset == 'mnist':
        train_loader, val_loader, test_loader = load_mnist_loaders(
            batch_size=args.batch_size, noise_level=args.label_noise_level,
            transform_function=transform_function,
            transform_validation=args.transform_validation,
            num_train_examples=args.num_train_examples)

    if args.dataset == 'cifar10':
        train_loader, val_loader, test_loader = load_cifar10_loaders(
            batch_size=args.batch_size, noise_level=args.label_noise_level,
            num_train_examples=args.num_train_examples,
            data_augmentation=args.data_augmentation,
            confusion_function=confusion_function)

    if args.dataset == 'clothing1M':
        train_loader, val_loader, test_loader = load_clothing1M_loaders(
            batch_size=args.batch_size,
            num_train_examples=args.num_train_examples,
            data_augmentation=args.data_augmentation)

    example_shape = train_loader.dataset[0][0].shape
    print("Dataset is loaded:\n\ttrain_samples: {}\n\tval_samples: {}\n\t"
          "test_samples: {}\n\tsample_shape: {}".format(
        len(train_loader.dataset), len(val_loader.dataset),
        len(test_loader.dataset), example_shape))

    return train_loader, val_loader, test_loader

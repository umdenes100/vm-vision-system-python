import torch
import torchvision.transforms as transforms
import PIL.Image

_mean = torch.Tensor([0.485, 0.456, 0.406]).cpu()
_std = torch.Tensor([0.229, 0.224, 0.225]).cpu()


def preprocess(image_bgr):
    """
    image_bgr: numpy array from OpenCV (BGR)
    returns: torch tensor [1, 3, H, W] normalized for ResNet18
    """
    # Convert BGR -> RGB for PIL
    image_rgb = image_bgr[:, :, ::-1]
    image = PIL.Image.fromarray(image_rgb)

    device = torch.device("cpu")
    t = transforms.functional.to_tensor(image).to(device)
    t.sub_(_mean[:, None, None]).div_(_std[:, None, None])
    return t[None, ...]

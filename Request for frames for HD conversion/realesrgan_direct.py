#!/usr/bin/env python3
"""
Real-ESRGAN upscaler - Direct PyTorch implementation
No basicsr dependency needed. Uses pre-trained models from GitHub.
"""

import torch
import torch.nn as nn
import cv2
import numpy as np
from pathlib import Path
import argparse
import urllib.request
import os
from typing import Tuple

# Architecture - RRDBNet from Real-ESRGAN
class RRDBNet(nn.Module):
    def __init__(self, num_in_ch, num_out_ch, num_feat=64, num_block=23, 
                 num_grow_ch=32, scale=4):
        super(RRDBNet, self).__init__()
        self.num_in_ch = num_in_ch
        self.num_out_ch = num_out_ch
        self.num_feat = num_feat
        self.num_block = num_block
        self.num_grow_ch = num_grow_ch
        self.scale = scale

        self.first_conv = nn.Conv2d(num_in_ch, num_feat, 3, 1, 1)
        self.body = nn.ModuleList()
        for _ in range(num_block):
            self.body.append(ResidualDenseBlock(num_feat, num_grow_ch))
        
        self.trunk = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        
        # Upsampling
        self.upsampler = nn.Sequential()
        for _ in range(int(np.log2(scale))):
            self.upsampler.add_module('up', nn.Sequential(
                nn.Conv2d(num_feat, num_feat * 4, 3, 1, 1),
                nn.PixelShuffle(2)
            ))
        
        self.final_conv = nn.Sequential(
            nn.Conv2d(num_feat, num_feat, 3, 1, 1),
            nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        )

    def forward(self, x):
        x = self.first_conv(x)
        trunk = x.clone()
        
        for block in self.body:
            x = block(x)
        
        x = self.trunk(x)
        x = x + trunk
        x = self.upsampler(x)
        x = self.final_conv(x)
        return x


class ResidualDenseBlock(nn.Module):
    def __init__(self, num_feat, num_grow_ch):
        super(ResidualDenseBlock, self).__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2*num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3*num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4*num_grow_ch, num_feat, 3, 1, 1)

    def forward(self, x):
        x1 = torch.relu(self.conv1(x))
        x2 = torch.relu(self.conv2(torch.cat([x, x1], 1)))
        x3 = torch.relu(self.conv3(torch.cat([x, x1, x2], 1)))
        x4 = torch.relu(self.conv4(torch.cat([x, x1, x2, x3], 1)))
        x5 = self.conv5(torch.cat([x, x1, x2, x3, x4], 1))
        return x5 * 0.2 + x


class RealESRGANUpscaler:
    """Real-ESRGAN upscaler using direct PyTorch models"""
    
    def __init__(self, scale=4, device='cpu', model_url=None):
        self.scale = scale
        self.device = device
        self.model = None
        self.load_model(model_url)
    
    def load_model(self, model_url=None):
        """Load Real-ESRGAN model weights"""
        if model_url is None:
            # Official Real-ESRGAN x4plus model
            model_url = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x4plus.pth'
        
        # Create architecture
        self.model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, 
                            num_block=23, num_grow_ch=32, scale=self.scale)
        
        # Download weights if needed
        weights_path = Path.home() / '.cache' / 'realesrgan' / 'model.pth'
        if not weights_path.exists():
            print(f"Downloading model ({model_url.split('/')[-1]})...")
            weights_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(model_url, weights_path)
            print(f"✓ Downloaded to {weights_path}")
        
        # Load weights
        state_dict = torch.load(weights_path, map_location=self.device)
        
        # Handle different state dict formats
        if 'params_ema' in state_dict:
            state_dict = state_dict['params_ema']
        elif 'params' in state_dict:
            state_dict = state_dict['params']
        
        self.model.load_state_dict(state_dict)
        self.model = self.model.to(self.device)
        self.model.eval()
        print(f"✓ Model loaded on {self.device}")
    
    def upscale(self, image_path: str, output_path: str = None, 
                tile_size: int = 400) -> Tuple[str, Tuple[int, int]]:
        """
        Upscale image with tiling for memory efficiency
        
        Args:
            image_path: Input image
            output_path: Output path (auto-generated if None)
            tile_size: Tile size for processing (lower = less VRAM)
        
        Returns:
            (output_path, new_dimensions)
        """
        img_path = Path(image_path)
        
        # Read image
        img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")
        
        h, w = img.shape[:2]
        print(f"  {img_path.name}: {w}x{h} → ", end="", flush=True)
        
        # Convert to tensor (RGB, normalized)
        img_tensor = torch.from_numpy(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).float()
        img_tensor = img_tensor.permute(2, 0, 1).unsqueeze(0) / 255.0
        
        # Upscale with tiling
        with torch.no_grad():
            if tile_size > 0 and (h > tile_size or w > tile_size):
                output = self._upscale_tiled(img_tensor, tile_size)
            else:
                output = self.model(img_tensor.to(self.device))
        
        # Convert back to image
        output = output.squeeze(0).permute(1, 2, 0).cpu().numpy()
        output = np.clip((output * 255).astype(np.uint8), 0, 255)
        output = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)
        
        new_h, new_w = output.shape[:2]
        print(f"{new_w}x{new_h}")
        
        # Save
        if output_path is None:
            output_path = str(img_path.parent / f"{img_path.stem}_4x{img_path.suffix}")
        
        os.makedirs(Path(output_path).parent, exist_ok=True)
        cv2.imwrite(output_path, output, [cv2.IMWRITE_JPEG_QUALITY, 95])
        
        return output_path, (new_w, new_h)
    
    def _upscale_tiled(self, img_tensor, tile_size):
        """Upscale large images by tiling"""
        b, c, h, w = img_tensor.shape
        tile_pad = 10
        
        output_h = h * self.scale
        output_w = w * self.scale
        output = torch.zeros(b, c, output_h, output_w, device=self.device)
        
        for i in range(0, h, tile_size):
            for j in range(0, w, tile_size):
                # Extract tile with padding
                ti_start = max(0, i - tile_pad)
                ti_end = min(h, i + tile_size + tile_pad)
                tj_start = max(0, j - tile_pad)
                tj_end = min(w, j + tile_size + tile_pad)
                
                tile = img_tensor[:, :, ti_start:ti_end, tj_start:tj_end].to(self.device)
                
                # Upscale tile
                with torch.no_grad():
                    tile_out = self.model(tile)
                
                # Place in output (accounting for padding)
                oi_start = ti_start * self.scale
                oi_end = ti_end * self.scale
                oj_start = tj_start * self.scale
                oj_end = tj_end * self.scale
                
                output[:, :, oi_start:oi_end, oj_start:oj_end] = tile_out
        
        return output
    
    def batch_upscale(self, input_dir: str, output_dir: str = None) -> list:
        """Batch upscale all images in directory"""
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"Directory not found: {input_dir}")
        
        if output_dir is None:
            output_dir = input_path / "upscaled_4x"
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Find images
        image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff', '.tif'}
        images = sorted([f for f in input_path.glob('*') 
                        if f.suffix.lower() in image_exts])
        
        if not images:
            print(f"⚠ No images found in {input_dir}")
            return []
        
        print(f"Found {len(images)} images. Upscaling 4x...")
        results = []
        
        for i, img_file in enumerate(images, 1):
            print(f"[{i}/{len(images)}] ", end="")
            
            out_file = output_path / f"{img_file.stem}_4x{img_file.suffix}"
            
            try:
                out, dims = self.upscale(str(img_file), str(out_file))
                results.append((str(img_file), out, dims))
            except Exception as e:
                print(f"✗ Error: {e}")
        
        print(f"\n✓ Done. Saved to: {output_dir}")
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Real-ESRGAN upscaler - 4K AI enhancement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single image, 4x upscale (1080p → 4320p)
  python realesrgan_direct.py photo.jpg
  
  # Batch process folder
  python realesrgan_direct.py --batch ./photos --output ./upscaled_4x
  
  # Use GPU if available
  python realesrgan_direct.py photo.jpg --gpu
        """
    )
    
    parser.add_argument('input', nargs='?', help='Input image or directory')
    parser.add_argument('--batch', action='store_true', help='Batch mode')
    parser.add_argument('--output', '-o', help='Output directory/file')
    parser.add_argument('--gpu', action='store_true', help='Use GPU (if available)')
    
    args = parser.parse_args()
    
    if not args.input:
        parser.print_help()
        return
    
    # Detect device
    device = 'cuda' if args.gpu and torch.cuda.is_available() else 'cpu'
    if args.gpu and device == 'cpu':
        print("⚠ GPU not available, using CPU")
    
    try:
        upscaler = RealESRGANUpscaler(scale=4, device=device)
        
        if args.batch:
            results = upscaler.batch_upscale(args.input, args.output)
            if results:
                print("\nResults:")
                for inp, out, dims in results:
                    print(f"  {Path(inp).name} → {dims[0]}x{dims[1]}")
        else:
            out, dims = upscaler.upscale(args.input, args.output)
            print(f"\n✓ Saved: {out}")
            print(f"  Resolution: {dims[0]}x{dims[1]}")
    
    except Exception as e:
        print(f"❌ Error: {e}", file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    main()
"""
Convert source icon to all needed formats for Napisy-TWON v2
"""

from PIL import Image
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_ICON = os.path.join(SCRIPT_DIR, "logo-mdb-surtitle-twon.png")


def main():
    print("Converting Napisy-TWON icon to all formats...")

    # Load source icon
    source = Image.open(SOURCE_ICON).convert('RGBA')
    print(f"  Source: {SOURCE_ICON} ({source.width}x{source.height})")

    # PNG sizes needed
    sizes = [16, 24, 32, 48, 64, 128, 256, 512]

    # Generate PNG files at each size
    for size in sizes:
        resized = source.resize((size, size), Image.Resampling.LANCZOS)
        filename = os.path.join(SCRIPT_DIR, f"icon_{size}.png")
        resized.save(filename, "PNG")
        print(f"  Created: icon_{size}.png")

    # Save main icon.png (256x256)
    main_icon = source.resize((256, 256), Image.Resampling.LANCZOS)
    main_icon.save(os.path.join(SCRIPT_DIR, "icon.png"), "PNG")
    print("  Created: icon.png (256x256)")

    # Create ICO file with multiple sizes
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_images = [source.resize((s, s), Image.Resampling.LANCZOS) for s in ico_sizes]

    ico_path = os.path.join(SCRIPT_DIR, "icon.ico")
    ico_images[0].save(
        ico_path,
        format='ICO',
        sizes=[(s, s) for s in ico_sizes],
        append_images=ico_images[1:]
    )
    print("  Created: icon.ico (multi-size: 16-256px)")

    # macOS ICNS would require additional tools, but we can note the sizes needed
    print("\nDone! All icons saved to:", SCRIPT_DIR)
    print("\nFor macOS .icns, use: iconutil or online converter with icon_512.png")


if __name__ == "__main__":
    main()

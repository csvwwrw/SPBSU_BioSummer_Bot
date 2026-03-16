import os

ENTRIES_DIR = 'entries'
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.webp'}


def rename_entries(base_dir: str) -> None:
    entries = sorted([
        e for e in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, e))
    ])

    for m, entry in enumerate(entries, start=1):
        entry_path = os.path.join(base_dir, entry)
        images = sorted([
            img for img in os.listdir(entry_path)
            if os.path.splitext(img)[1].lower() in IMAGE_EXTENSIONS
        ])

        for n, image in enumerate(images, start=1):
            src = os.path.join(entry_path, image)
            ext = os.path.splitext(image)[1].lower()
            dst = os.path.join(entry_path, f'{n}{ext}')
            os.rename(src, dst)

        os.rename(entry_path, os.path.join(base_dir, f'PACK_{m}'))
        print(f'Renamed: {entry} → PACK_{m} ({len(images)} images)')


if __name__ == '__main__':
    rename_entries(ENTRIES_DIR)

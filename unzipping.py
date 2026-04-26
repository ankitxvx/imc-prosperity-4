from pathlib import Path
import zipfile
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time

WATCH_DIR = Path(r"C:\\Users\\ankit\Desktop\\IMC prosperity 4\\round 4")
OUTPUT_DIR = Path(r"C:\\Users\\ankit\\Desktop\\IMC prosperity 4\\round 4\\output_log")

WATCH_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

processed_files = set()

def unzip_file(zip_path: Path):
    if zip_path in processed_files:
        return

    target_dir = OUTPUT_DIR / zip_path.stem
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)

        processed_files.add(zip_path)
        print(f"Extracted: {zip_path.name}")

        # Delete zip file after successful extraction
        zip_path.unlink()
        print(f"Deleted: {zip_path.name}")

    except zipfile.BadZipFile:
        print(f"Invalid zip: {zip_path.name}")
    except Exception as e:
        print(f"Error extracting {zip_path.name}: {e}")

def process_existing_files():
    for zip_file in WATCH_DIR.glob("*.zip"):
        unzip_file(zip_file)

class ZipHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".zip"):
            time.sleep(1)  # wait for file copy to finish
            unzip_file(Path(event.src_path))

if __name__ == "__main__":
    print(f"Watching: {WATCH_DIR}")

    # Unzip already existing zip files first
    process_existing_files()

    # Then watch for new ones
    observer = Observer()
    observer.schedule(ZipHandler(), str(WATCH_DIR), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()
#!/usr/bin/env python3
import argparse
from pathlib import Path
import subprocess
import tempfile
from typing import Dict

from ddl_processor import DatabaseType, process_ddl_files


# Repository details
REPO_URL = "https://github.com/IHE-SDC-WG/OHDSI-CommonDataModel-SDC.git"
TARGET_PATH = "inst/ddl/5.4-SDC"
DEFAULT_COMMIT = "3faab12004b98a23fd2db5de9acfad78c10220ed"

# Supported database types and their source folders
SUPPORTED_DBS = {DatabaseType.POSTGRESQL: "postgresql", DatabaseType.SQLITE: "sqlite"}

# Required files for processing
REQUIRED_FILES = ["ddl", "primary_keys", "constraints", "indices"]


def fetch_ddl_files(commit: str, temp_dir: Path) -> Path:
    """Clone repository and checkout specific commit"""
    repo_dir = temp_dir / "repo"
    print("Cloning repository...")
    subprocess.run(
        ["git", "clone", "--no-checkout", REPO_URL, str(repo_dir)],
        check=True,
    )

    print(f"Checking out commit {commit}...")
    subprocess.run(["git", "checkout", commit], cwd=repo_dir, check=True)

    target_dir = repo_dir / TARGET_PATH
    if not target_dir.is_dir():
        raise RuntimeError(
            f"Target path '{TARGET_PATH}' does not exist in commit {commit}."
        )

    return target_dir


def get_input_files(source_dir: Path, db_folder: str) -> Dict[str, str]:
    """Get paths to input files for a specific database type"""
    db_dir = source_dir / db_folder
    if not db_dir.is_dir():
        raise RuntimeError(f"Database directory {db_folder} not found")

    # Map each required file type to its full path
    return {
        file_type: str(next(db_dir.glob(f"*{file_type}.sql")))
        for file_type in REQUIRED_FILES
    }


def write_processed_files(
    processed_files: Dict[str, str], output_dir: Path, db_type: DatabaseType
):
    """Write processed files to output directory"""
    db_output_dir = output_dir / SUPPORTED_DBS[db_type]
    db_output_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in processed_files.items():
        (db_output_dir / filename).write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and process DDL files from a Git repository."
    )
    parser.add_argument(
        "commit_hash",
        nargs="?",
        default=DEFAULT_COMMIT,
        help=f"Git commit hash to fetch DDL files from (default: {DEFAULT_COMMIT})",
    )
    args = parser.parse_args()

    # Set up paths
    script_dir = Path(__file__).parent
    output_dir = script_dir / "ddl"

    # Create temporary directory for git operations
    with tempfile.TemporaryDirectory() as tmp_dir:
        source_dir = fetch_ddl_files(args.commit_hash, Path(tmp_dir))

        # Process each supported database type
        for db_type in SUPPORTED_DBS:
            print(f"\nProcessing {db_type.name} DDL files...")
            try:
                # Get input files for this database type
                input_files = get_input_files(source_dir, SUPPORTED_DBS[db_type])

                # Process the files
                processed_files = process_ddl_files(input_files, db_type)

                # Write processed files
                write_processed_files(processed_files, output_dir, db_type)
                print(f"Successfully processed {db_type.name} DDL files")

            except Exception as e:
                print(f"Error processing {db_type.name} DDL files: {e}")
                continue

    print("\nAll operations completed successfully.")


if __name__ == "__main__":
    main()

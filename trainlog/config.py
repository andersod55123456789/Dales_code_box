import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(APP_DIR, "trainlog")
DATA_DIR = os.path.join(APP_DIR, "data")
BACKUP_DIR = os.path.join(APP_DIR, "backups")
DATABASE_PATH = os.path.join(DATA_DIR, "training.db")
PROGRAM_YAML = os.path.join(APP_DIR, "program.yaml")
PROGRAM_MD = os.path.join(os.path.dirname(APP_DIR), "PROGRAM.md")
SCHEMA_SQL = os.path.join(PKG_DIR, "schema.sql")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday"]

"""FairFace labels: who is in each photo (race, gender, age group), never what they feel.

The official label file (fairface_label_val.csv) has one row per photo:
file,age,gender,race,service_test  e.g.  val/1.jpg,3-9,Male,East Asian,False
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

RACES = (
    "Black",
    "East Asian",
    "Indian",
    "Latino_Hispanic",
    "Middle Eastern",
    "Southeast Asian",
    "White",
)
GENDERS = ("Female", "Male")
AGES = ("0-2", "3-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-69", "more than 70")
VALUES = {"race": RACES, "gender": GENDERS, "age": AGES}


@dataclass(frozen=True)
class Photo:
    file: str  # path relative to the images folder, e.g. val/1.jpg
    race: str
    gender: str
    age: str


def read_labels(path: Path) -> list[Photo]:
    """Every row, checked: an unknown group name is an error, not a new group."""
    photos = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        missing = {"file", "race", "gender", "age"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            for attribute, allowed in VALUES.items():
                if row[attribute] not in allowed:
                    raise ValueError(f"{path}:{line}: unknown {attribute} {row[attribute]!r}")
            photos.append(Photo(row["file"], row["race"], row["gender"], row["age"]))
    if not photos:
        raise ValueError(f"{path} has no rows")
    return photos

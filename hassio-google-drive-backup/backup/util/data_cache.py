from datetime import timedelta
from enum import Enum, unique
from backup.config import Config, Setting, VERSION, Version
from injector import inject, singleton
from ..time import Time
from typing import Dict
import json
import os

KEY_BACKUPS = "snapshots"
KEY_I_MADE_THIS = "i_made_this"
KEY_PENDING = "pending"
KEY_CREATED = "created"
KEY_IGNORE = "ignore"
KEY_LAST_SEEN = "last_seen"
KEY_NAME = "name"
KEY_LAST_VERSION = "last_verison"
KEY_UPGRADES = "upgrades"

CACHE_EXPIRATION_DAYS = 30


@unique
class UpgradeFlags(Enum):
    DONT_IGNORE_LEGACY_SNAPSHOTS = "include_legacy_snapshots",


@singleton
class DataCache:
    @inject
    def __init__(self, config: Config, time: Time):
        self._config = config
        self._data = {}
        self._dirty = {}
        self._time = time
        self._last_version = Version.default()
        self._flags = set()
        self._load()

    def _load(self):
        if not os.path.isfile(self._config.get(Setting.DATA_CACHE_FILE_PATH)):
            self._data = {KEY_BACKUPS: {}}
        else:
            with open(self._config.get(Setting.DATA_CACHE_FILE_PATH)) as f:
                self._data = json.load(f)

        # Check for an upgrade.
        if KEY_LAST_VERSION in self._data:
            self._last_version = Version.parse(self._data[KEY_LAST_VERSION])
        if self.previousVersion != self.currentVersion:
            # add an upgrade marker
            if KEY_UPGRADES not in self._data:
                self._data[KEY_UPGRADES] = []
            self._data[KEY_UPGRADES].append({
                'prev_version': str(self.previousVersion),
                'new_version': str(self.currentVersion),
                'date': self._time.now().isoformat()
            })
            self._data[KEY_LAST_VERSION] = str(self.currentVersion)
            self.makeDirty()
            self.saveIfDirty()

        if self.previousVersion == Version.default() and self.currentVersion > Version.parse("0.103"):
            self._flags.add(UpgradeFlags.DONT_IGNORE_LEGACY_SNAPSHOTS)

    def save(self, data=None):
        if data is None:
            data = self._data
        with open(self._config.get(Setting.DATA_CACHE_FILE_PATH), "w") as f:
            json.dump(data, f, indent=4)
        self._dirty = False

    def makeDirty(self):
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def backups(self) -> Dict[str, Dict[str, str]]:
        if KEY_BACKUPS not in self._data:
            self._data[KEY_BACKUPS] = {}
        return self._data[KEY_BACKUPS]

    def backup(self, slug) -> Dict[str, str]:
        if slug not in self.backups:
            self.backups[slug] = {}
        return self.backups[slug]

    def saveIfDirty(self):
        if self._dirty:
            # See if we need to remove any old entries
            for slug in list(self.backups.keys()):
                data = self.backups[slug].get(KEY_LAST_SEEN)
                if data is not None and self._time.now() > self._time.parse(data) + timedelta(days=CACHE_EXPIRATION_DAYS):
                    del self.backups[slug]
            self.save()

    @property
    def previousVersion(self):
        return self._last_version

    @property
    def currentVersion(self):
        return Version.parse(VERSION)

    def checkFlag(self, flag: UpgradeFlags):
        return flag in self._flags

    def getUpgradeTime(self, version: Version):
        for upgrade in self._data[KEY_UPGRADES]:
            if Version.parse(upgrade['new_version']) >= version:
                return self._time.parse(upgrade['date'])
        return self._time.now()

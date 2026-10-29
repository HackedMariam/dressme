"""Échantillonnage des ressources pendant un appel : VRAM (nvidia-smi) et RAM (psutil)."""

import subprocess
import threading

import psutil


def sample_vram_mib():
    """VRAM utilisée (Mio) sur le premier GPU, ou None si nvidia-smi est indisponible."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5, check=True).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def sample_ram_available_mib():
    return psutil.virtual_memory().available / (1024 * 1024)


class ResourceMonitor:
    """Contexte : échantillonne toutes les `interval` secondes ; garde les extrêmes.

    1 s par défaut (0,25 s lors du benchmark initial) : chaque échantillon lance
    un processus nvidia-smi, ce qui ajoute de la pression mémoire.
    """

    def __init__(self, interval=1.0, vram_sampler=sample_vram_mib, ram_sampler=sample_ram_available_mib):
        self.interval = interval
        self.vram_sampler = vram_sampler
        self.ram_sampler = ram_sampler
        self.vram_peak_mib = None
        self.ram_min_available_mib = None
        self.samples = 0
        self._stop = threading.Event()
        self._thread = None

    def _sample(self):
        vram = self.vram_sampler()
        ram = self.ram_sampler()
        if vram is not None:
            self.vram_peak_mib = vram if self.vram_peak_mib is None else max(self.vram_peak_mib, vram)
        if ram is not None:
            self.ram_min_available_mib = ram if self.ram_min_available_mib is None else min(self.ram_min_available_mib, ram)
        self.samples += 1

    def _run(self):
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self.interval)

    def __enter__(self):
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=10)
        self._sample()
        return False

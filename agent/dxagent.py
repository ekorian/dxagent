"""
dxagent.py

   This file contains the core of dxagent

@author: K.Edeline

"""

import sched
import time
import signal
import importlib

from .constants import AGENT_INPUT_PERIOD
from .core.ios import IOManager
from .core.daemon import Daemon
from .input.sysinfo import SysInfo
from .input.bm_input import BMWatcher
from .input.vm_input import VMWatcher
from .input.vpp_input import VPPWatcher
from .assurance.health import HealthEngine
from .gnmi.exporter import DXAgentExporter

class DXAgent(Daemon, IOManager):
   """
   DXAgent

   
   """

   def __init__(self, parse_args=True):
      Daemon.__init__(self, pidfile='/var/run/dxagent.pid',
                      stdout='/var/log/dxagent.log', 
                      stderr='/var/log/dxagent.log',
                      name='dxagent',
                      input_rate=AGENT_INPUT_PERIOD)
      IOManager.__init__(self, child=self, parse_args=parse_args)

      self.load_ios()
      if not parse_args:
         return

   def _init(self):
      self.sysinfo = SysInfo()
      self.scheduler = sched.scheduler()

      # ringbuffers are stored here
      self._data = {}

      # SharedMemory with dxtop.
      # Drop privileges to avoid dxtop root requirements
      if not self.args.disable_shm:
         mod = importlib.import_module("agent.core.shareablebuffer")     
         with self.drop():
            self.sbuffer = getattr(mod, "ShareableBuffer")(create=True)

      # watchers.
      self.bm_watcher = BMWatcher(self._data, self.info, self)
      self.vm_watcher = VMWatcher(self._data, self.info, self)
      self.vpp_watcher = VPPWatcher(self._data, self.info, self)

      # health engine
      self.engine = HealthEngine(self._data, self.info, self)

      # exporter
      if self.gnmi_target:
         self.exporter = DXAgentExporter(self._data, self.info, self,
                                         target_url=self.gnmi_target)
         self.exporter.run()

      # catch signal for cleanup
      signal.signal(signal.SIGTERM, self.exit)

   def _input(self):
      self.bm_watcher.input()
      self.vm_watcher.input()
      self.vpp_watcher.input()

   def process(self):
      """
      read input data, process and write it to shmem.
      re-schedule itself.

      """
      # fetch input
      self._input()
      # compute metrics&symptoms from input
      self.engine.update_health()
      # write to shmem
      if not self.args.disable_shm:
         skip=["stats"] if not self.args.verbose else []
         self.sbuffer.write(self._data, skip=skip, info=self.info)
      #self.info(list(self.exporter._iterate_data()))
      self.scheduler.enter(AGENT_INPUT_PERIOD,0,self.process)

   def exit(self, signum=None, stackframe=None):
      """
      cleanup before exiting

      """
      self.running = False
      time.sleep(AGENT_INPUT_PERIOD)

      self.bm_watcher.exit()
      self.vm_watcher.exit()
      self.vpp_watcher.exit()
      if not self.args.disable_shm:
         self.sbuffer.unlink()
         del self.sbuffer

   def run(self):
      """
      main function

      """
      self._init()
      self.running = True

      self.info(self.sysinfo)
      self.process()

      while self.running:
         self.scheduler.run(blocking=False)
         time.sleep(AGENT_INPUT_PERIOD)


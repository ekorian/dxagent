"""
vm_input.py

   Input parsing for virtual machines health monitoring

@author: K.Edeline
"""

import os

# list of supported vm api libs
vm_libs=[]

try:
   import virtualbox
   from virtualbox.library import MachineState
   import vboxapi
   vm_libs.append("virtualbox")
except:
   pass

from ..core.rbuffer import init_rb_dict

# vbox states without pseudo-states
_virtualbox_states = [
      'Null','PoweredOff','Saved','Teleported','Aborted','Running','Paused', 
      'Stuck','Teleporting','LiveSnapshotting','Starting', 'Stopping', 
      'Saving','Restoring', 'TeleportingPausedVM', 'TeleportingIn', 
      'FaultTolerantSyncing', 'DeletingSnapshotOnline','DeletingSnapshotPaused',
      'OnlineSnapshotting','RestoringSnapshot', 'DeletingSnapshot','SettingUp',
      'Snapshotting'
   ]

"""
   Time interval in seconds between two consecutive samples of
   performance data.
"""
_virtualbox_metrics_sampling_period = 1

"""
   Number of samples to retain in performance data history. Older
   samples get discarded.
"""
_virtualbox_metrics_sampling_count = 1

def hypervisors_support():
   """
   @return vbox_supported
   """
   return "virtualbox" in vm_libs

class VMWatcher():

   def __init__(self, data, info, parent):
      self._data=data
      self.info=info
      self.parent=parent

      if "virtualbox" in vm_libs:
         #
         # Drop privileges & Change config dir to acquire a IVirtualbox.
         #
         # virtualbox vm management is user-based, and root is,
         # by design, not supposed to access a user VMs.
         # Still, it is achievable by setting the user ruid and euid
         # when acquiring the IVirtualBox instance.
         # Plus, config dir is used to access virtualbox settings file
         # instance.
         with self.parent.drop(self.parent.config["virtualbox"]["vbox_user"]) as _, \
              self.parent.switch_config_home(self.parent.config
                            ["virtualbox"]["config_directory"]) as _:
            self._vbox = virtualbox.VirtualBox()

         self.vbox_system_properties = self._vbox.system_properties
         # setup performance metric collection for all vms
         self.vbox_perf = self._vbox.performance_collector # IPerformanceCollecto
         self.vbox_perf.setup_metrics(['*:'], # all metrics without aggregates
                self._vbox.machines, _virtualbox_metrics_sampling_period, 
                                     _virtualbox_metrics_sampling_count)

         attr_list = ["version", "vm_count"]
         attr_types = [str, int]
         self._data["virtualbox/system"] = init_rb_dict(attr_list, 
                                                types=attr_types)
         self._data["virtualbox/vms"] = {}
         self.vbox_vm_count = 0

   def imports(self):
      """
      Ensure that all machines in vbox machine_folder are
      registered

      if default_folder is not set: 
            $sudo vboxmanage setproperty machinefolder
      """
      machine_folder = self.vbox_system_properties.default_machine_folder
      machine_dirs = [d for d in os.listdir(machine_folder)
                        if os.path.isdir(os.path.join(machine_folder,d))]
      registered = [m.name for m in self._vbox.machines]
      for d in machine_dirs:

         path = os.path.join(machine_folder, d)
         # find .vbox setting file
         sfiles = [os.path.join(path,s) for s in os.listdir(path) 
            if s.endswith("vbox") and os.path.isfile(os.path.join(path,s))]
         for sfile in sfiles:
            if d in registered:
               continue
            self._vbox.register_machine(self._vbox.open_machine(sfile))
            self.info("vbox: registered {}".format(d))

   def exit(self):
      """
      exit vmwatcher gracefuly

      """
      if "virtualbox" in vm_libs:
         del self._vbox
         self._vbox = None

   def virtualbox_vm_is_active(self, machine):
      state = machine.state
      return (state >= MachineState.first_online
            and state <= MachineState.last_online)

   def input(self):
      if "virtualbox" in vm_libs:
         #self._input_virtualbox()
         try:
            self._input_virtualbox()
            #pass
         except:
            pass
         finally:
            if self._vbox:
               self._post_input_virtualbox()

   def _post_input_virtualbox(self):
      """
      renew registration to metric collection for all machines

      """
      self.vbox_perf.setup_metrics(['*:'], self._vbox.machines, 
            _virtualbox_metrics_sampling_period, 
            _virtualbox_metrics_sampling_count)

   def _input_virtualbox(self):
      """
      VM (virtualbox)
         VBoxManage showvminfo
         VBoxManage bandwidthctl
         VBoxManage storagectl
         VBoxManage metrics
      #sys = self._vbox.system_properties#ISystemProperties 
      #hds = self._vbox.hard_disks#IMedium 

      """

      attr_list = ["cpu", "state", "accessible", "id", "os_type_id", "cpu_cap", 
         "mem_size", "vram_size", "firmware", "chipset", "session_state", 
         "session_name", "session_pid",  "last_state_change",  "snapshot_count",
         "io_cache_enabled",  "io_cache_size", "/VirtualBox/GuestInfo/Net/Count"
      ] + [ 
         'CPU/Load/User', 'CPU/Load/Kernel', 'RAM/Usage/Used',
         'Disk/Usage/Used', 'Net/Rate/Rx', 'Net/Rate/Tx',
         'Guest/CPU/Load/User','Guest/CPU/Load/Kernel', 'Guest/CPU/Load/Idle',
         'Guest/RAM/Usage/Total', 'Guest/RAM/Usage/Free',
         'Guest/RAM/Usage/Balloon', 'Guest/RAM/Usage/Shared',
         'Guest/RAM/Usage/Cache', 'Guest/Pagefile/Usage/Total',
      ]
      unit_list = [ '','','','','','','MB','MB','','','','','','','','','','',
         '%', '%', 'kB', 'mB', 'B/s',
         'B/s', '%', '%', '%',
         'kB', 'kB', 'kB', 'kB', 'kB', 'kB', 
      ]
      type_list = [ int, str, str, str, str, int, int, int, str, str, str,
         str, str, str, str, str, int, int, float, float, float,
         float, float, float, float, float, float, float, float,
         float, float, float, float,
      ]

      self._data["virtualbox/system"]["version"].append(self._vbox.version_normalized)
      self.vbox_vm_count = 0
      
      for m in self._vbox.machines:
         name = m.name
         state = _virtualbox_states[int(m.state)]
         
         # check if machine is online/offline
         if not self.virtualbox_vm_is_active(m):
            # if it went inactive, update state only
            if name in self._data["virtualbox/vms"]:
            #   del self._data["virtualbox/vms"][name]
               self._data["virtualbox/vms"][name]["state"].append(state)
            continue
         
         self.vbox_vm_count += 1
         # add entry if needed
         self._data["virtualbox/vms"].setdefault(name, init_rb_dict(attr_list, 
               types=type_list, units=unit_list))
         #sc=m.storage_controllers # IStorageController
         vm_attrs = [
            ("cpu", str(m.cpu_count)),
            ("state", state), 
            ("accessible", str(int(m.accessible))),
            ("id", m.id_p), ("os_type_id",m.os_type_id),
            ("cpu_cap", str(m.cpu_execution_cap)), 
            ("mem_size", str(m.memory_size)), 
            ("vram_size", "0"),#str(m.vram_size)),
            ("firmware", str(m.firmware_type)), 
            ("chipset", str(m.chipset_type)),
            ("session_state", str(m.session_state)), 
            ("session_name", m.session_name), 
            ("session_pid", str(m.session_pid)), 
            ("last_state_change", str(m.last_state_change)), 
            ("snapshot_count", str(m.snapshot_count)), 
            ("io_cache_enabled", str(int(m.io_cache_enabled))),
            ("io_cache_size", str(m.io_cache_size)) 
         ]

         # probe for guest networks
         guestinfo_prefix="/VirtualBox/GuestInfo/Net/"
         net_count =  m.get_guest_property(guestinfo_prefix+"Count")[0]
         vm_attrs.append(("/VirtualBox/GuestInfo/Net/Count", net_count))

         # probe for guest metrics
         val, metric_attrs, _, _, scales, _, _, _ = self.vbox_perf.query_metrics_data(
               ['*:'], [m])
         vm_attrs.extend([(attr, str(val[i]/scales[i])) 
                  for i,attr in enumerate(metric_attrs)])
         
         for k,d in vm_attrs: 
            if not d:
               continue
            self._data["virtualbox/vms"][name][k].append(d)

         # add rest of probed input (the variable bit)
         attrs_suffix = ["Name", "MAC", "V4/IP", "V4/Broadcast",
                             "V4/Netmask", "Status"]
         for net in range(int(net_count)):
            attrs_list = ["{}{}/{}".format(guestinfo_prefix, net, attr) 
                           for attr in attrs_suffix]
            # add entry if needed
            if attrs_list[0] not in self._data["virtualbox/vms"][name]:
               self._data["virtualbox/vms"][name].update(init_rb_dict(
                  attrs_list, type=str))

            for attr in attrs_list:
               d = str(m.get_guest_property(attr)[0])
               if not d:
                  continue
               self._data["virtualbox/vms"][name][attr].append(d)

      self._data["virtualbox/system"]["vm_count"].append(self.vbox_vm_count)
      


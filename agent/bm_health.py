"""
bm_health.py

   Input parsing for baremetal health monitoring

@author: K.Edeline
"""

import os
import netifaces
import time
import ipaddress
from agent.buffer import init_rb_dict

class BMWatcher():

   def __init__(self, data, info):
      self.msec_per_jiffy = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
      self._data = data
      self.info = info
      self._init_dicts()

   def _init_dicts(self):

      # init categories whose input count are prone to change during execution
      # e.g., interfaces , processes
      self._data["net/dev"] = {}
      self._data["bm_ifs"] = {}
      self._data["swaps"] = {}
      self._data["net/arp"] = {}
      self._data["stats"] = {}

      # uptime
      attr_list = ["up", "idle"]
      self._data["uptime"] = init_rb_dict(attr_list, type=str)

      # stats_global
      attr_list = ["proc_count", "run_count", "sleep_count", "wait_count", 
         "stopped_count", "ts_count", "dead_count",
         "zombie_count", "parked_count", "idle_count"]
      self._data["stats_global"] = init_rb_dict(attr_list)

      # loadavg
      attr_list = ["1min", "5min", "15min", "runnable", "total"]
      self._data["loadavg"] = init_rb_dict(attr_list,type=float)

      # meminfo
      attr_list, unit_list = [], []
      with open("/proc/meminfo", 'r') as f:
         for l in f.readlines():
            elements=l.rstrip().split()
            attr_list.append(elements[0].rstrip(':'))
            unit_list.append(elements[2] if len(elements)>2 else None)
      self._data["meminfo"] = init_rb_dict(attr_list, units=unit_list)

      # netstat
      attr_list = []
      with open("/proc/net/netstat", 'r') as f:
         while True:
            attrs = f.readline().split()
            _ = f.readline()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')
            attr_list.extend([prefix+attr for attr in attrs])
      self._data["netstat"] = init_rb_dict(attr_list, counter=True)

      # snmp
      attr_list = []
      with open("/proc/net/snmp", 'r') as f:
         while True:
            attrs = f.readline().split()
            _ = f.readline()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')
            attr_list.extend([prefix+attr for attr in attrs])
      self._data["snmp"] = init_rb_dict(attr_list, counter=True)


      # stat and stat/cpu
      attr_list = []
      attr_list_cpu = ["user", "nice", "system", "idle", "iowait",
                        "irq", "softirq", "steal", "guest", "guest_nice"]
      self._data["stat/cpu"] = {}
      with open("/proc/stat", 'r') as f:
         for l in f.readlines():
            label = l.split()[0]

            if label.startswith("cpu"):
               self._data["stat/cpu"][label] = init_rb_dict(attr_list_cpu)
            else:
               attr_list.append(label)

      # XXX not portable
      is_counter = [True, True, True, False, False, False, True]
      self._data["stat"] = init_rb_dict(attr_list, counters=is_counter)

      # proc/stat
      attr_list = [
         "net.core.rmem_default", "net.core.rmem_max", "net.core.wmem_default",
         "net.core.wmem_max", "net.ipv4.tcp_mem_min", "net.ipv4.tcp_mem_pressure",
         "net.ipv4.tcp_mem_max", "net.ipv4.tcp_rmem_min", "net.ipv4.tcp_rmem_default",
         "net.ipv4.tcp_rmem_max", "net.ipv4.tcp_wmem_min", "net.ipv4.tcp_wmem_default",
         "net.ipv4.tcp_wmem_max", "net.core.default_qdisc", "net.core.netdev_max_backlog", 
         "net.ipv4.tcp_congestion_control", "net.ipv4.tcp_sack", "net.ipv4.tcp_dsack", 
         "net.ipv4.tcp_fack", "net.ipv4.tcp_syn_retries", 
         "net.ipv4.tcp_slow_start_after_idle", "net.ipv4.tcp_retries1", 
         "net.ipv4.tcp_retries2", "net.ipv4.tcp_mtu_probing", 
         "net.ipv4.tcp_max_syn_backlog", "net.ipv4.tcp_base_mss", 
         "net.ipv4.tcp_min_snd_mss", "net.ipv4.tcp_ecn_fallback", "net.ipv4.tcp_ecn", 
         "net.ipv4.tcp_adv_win_scale", "net.ipv4.tcp_window_scaling", 
         "net.ipv4.tcp_tw_reuse", "net.ipv4.tcp_syncookies", "net.ipv4.tcp_timestamps", 
         "net.ipv4.tcp_no_metrics_save", "net.ipv4.ip_forward", "net.ipv4.ip_no_pmtu_disc", 
      ]
      unit_list = [
         "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", 
         "B", "B", "B", "", "", "", "", "", "", "", "", "", "", "", "", 
         "", "", "", "", "", "", "", "", "", "", "", ""
      ]
      self._data["proc/sys"] =  init_rb_dict(attr_list, units=unit_list, type=str)

      # rt-cache read attrs
      self._data["rt-cache"] = {}
      with open("/proc/net/stat/rt_cache", 'r') as f:
         attr_list_rt_cache = f.readline().split()
         cpu_count = len(f.readlines())

      # arp-cache read attrs
      self._data["arp-cache"] = {}
      with open("/proc/net/stat/arp_cache", 'r') as f:
         attr_list_arp_cache = f.readline().split()

      # ndisc-cache read attrs
      self._data["ndisc-cache"] = {}
      with open("/proc/net/stat/ndisc_cache", 'r') as f:
         attr_list_ndisc_cache = f.readline().split()

      # generate dict for each cpu
      for i in range(cpu_count):
         cpu_label="cpu{}".format(i)

         self._data["rt-cache"][cpu_label] = init_rb_dict(attr_list_rt_cache, type=int)
         self._data["arp-cache"][cpu_label] = init_rb_dict(attr_list_arp_cache, type=int)
         self._data["ndisc-cache"][cpu_label] = init_rb_dict(attr_list_ndisc_cache, type=int)
      
   def input(self):
      """
      baremetal health: Linux

      """

      """
      parse input from

      /proc/<PID>/stat k
      /proc/stat + stat/cpu k
      /proc/meminfo k
      /proc/loadavg       k
      /proc/swaps      k
      /proc/uptime k
      /proc/diskstats
      /proc/net/netstat k
      /proc/net/snmp k
      /proc/net/stat/arp_cache k
      /proc/net/stat/ndisc_cache k
      /proc/net/stat/rt_cache k
      /proc/net/dev (interfaces listed in /sys/class/net/*) k
      /sys/class/net/enp4s0/ k

      /proc/net/tcp
      /proc/net/udp
      /proc/net/unix

      /proc/net/arp k
      /proc/net/route k
      """
      self._process_proc_meminfo()
      self._process_proc_stat()
      self._process_proc_stats()
      self._process_proc_loadavg()
      self._process_proc_swaps()
      self._process_proc_uptime()
      self._process_proc_diskstats()
      self._process_proc_net_netstat()
      self._process_proc_net_snmp()
      self._process_proc_net_stat_arp_cache()
      self._process_proc_net_stat_ndisc_cache()
      self._process_proc_net_stat_rt_cache()
      self._process_proc_net_dev()
      self._process_proc_net_arp()
      self._process_proc_net_route()
      self._process_net_settings()

      # non-standards
      self._process_interfaces()

   def _process_proc_meminfo(self):
      with open("/proc/meminfo", 'r') as f:
         for l in f.readlines():
            elements = l.rstrip().split()
            self._data["meminfo"][elements[0].rstrip(':')].append(elements[1])

   def _process_proc_stats(self):
      attr_names = [ "comm", "state", "ppid", "pgrp", "sid",
                     "tty_nr", "tty_pgrp", "flags", "min_flt", "cmin_flt",
                     "maj_flt", "cmaj_flt", "utime", "stime", "cutime",
                     "cstime", "priority", "nice", "num_threads", "itrealvalue",
                     "starttime", "vsize", "rss", "rsslim", "startcode",
                     "endcode", "startstack", "kstk_esp", "kstk_eip", "signal",
                     "blocked", "sigignore", "sigcatch", "wchan", "nswap",
                     "cnswap", "exit_signal", "processor", "rt_priority",
                     "policy", "delayacct_blkio_ticks", "gtime", 
                     "cgtime"]
      attr_types = 2*[str] + 41*[int]

      root_dir = "/proc/"
      proc_state = {"R":0, "S":0, "D":0, "T":0, "t":0, "X":0, "Z":0,
                    "P":0,"I": 0, }
      active_procs = []
      for d in next(os.walk(root_dir))[1]:

         # not a proc
         if not d.isdigit():
            continue

         path = root_dir+d+"/stat"
         try:
            with open(path, 'r') as f:
               line = f.readline().rstrip()
               split = line.split('(')
               pid = split[0].rstrip()
               split = split[-1].split(')')
               comm = split[0]

               # create new rb if needed
               if pid not in self._data["stats"]:
                  self._data["stats"][pid] = init_rb_dict(attr_names, types=attr_types)

               # READ 
               for i,e in enumerate( ([comm]+split[-1].split())[:len(attr_names)] ):
                  self._data["stats"][pid][attr_names[i]].append(e)
            
            active_procs.append(pid)
            proc_state[self._data["stats"][pid]["state"].top()] += 1
         except:
            pass

      # cleanup expired procs
      for monitored_pid in list(self._data["stats"].keys()):
         if monitored_pid not in active_procs:
            del self._data["stats"][monitored_pid]

      # count procs
      self._data["stats_global"]["proc_count"].append(len(self._data["stats"]))
      # count proc states
      proc_state_names = {"R":"run_count", "S":"sleep_count", "D":"wait_count", 
         "T":"stopped_count", "t":"ts_count",   "X":"dead_count",
         "Z":"zombie_count", "P":"parked_count", "I":"idle_count",
      }
      for d,v in proc_state.items():
         self._data["stats_global"][proc_state_names[d]].append(v)
      

   def _process_proc_stat(self):
      attr_names = ["user", "nice", "system", "idle", "iowait",
                    "irq", "softirq", "steal", "guest", "guest_nice"]

      with open("/proc/stat", 'r') as f:
         for l in f.readlines():
            if l.startswith("cpu"):
               split = l.rstrip().split()
               cpu_label = split[0]
               for i,e in enumerate(split[1:]):
                  self._data["stat/cpu"][cpu_label][attr_names[i]].append(e)

            else:
               k, d = l.rstrip().split()[:2]
               self._data["stat"][k].append(d)

   def _process_proc_loadavg(self):
      attr_names = ["1min", "5min", "15min", "runnable", "total"]

      with open("/proc/loadavg", 'r') as f:
         for i, e in enumerate(f.readline().rstrip().split()):
            if i == 3:
               vals = e.split('/')
               self._data["loadavg"][attr_names[i]].append(vals[0])
               self._data["loadavg"][attr_names[i+1]].append(vals[1])
               break
            else:
               self._data["loadavg"][attr_names[i]].append(e)

   def _process_proc_swaps(self):
      """
      index is swap filename
      """

      attr_names = ["type", "size", "used", "priority"]
      active_swaps = []
      with open("/proc/swaps", 'r') as f:
         for l in f.readlines()[1:]:
            split = l.rstrip().split()

            # create swap if needed
            swap_label = split[0]
            active_swaps.append(swap_label)
            if swap_label not in self._data["swaps"]:
               self._data["swaps"][swap_label] = init_rb_dict(attr_names, type=str)

            for i,e in enumerate(split[1:]):
               self._data["swaps"][swap_label][attr_names[i]].append(e)

      # cleanup unmounted/deleted swaps
      for monitored_swaps in list(self._data["swaps"].keys()):
         if monitored_swaps not in active_swaps:
            del self._data["swaps"][monitored_swaps]

   def _process_proc_uptime(self):
      attr_names = ["up", "idle"]

      with open("/proc/uptime", 'r') as f:
         for i,e in enumerate(f.readline().rstrip().split()):
            self._data["uptime"][attr_names[i]].append(e)

   def _process_proc_diskstats(self):
      attr_names = []
      with open("/proc/diskstats", 'r') as f:
         self._data["diskstats"] = [l.rstrip().split() for l in f.readlines()]

   def _process_proc_net_netstat(self):

      with open("/proc/net/netstat", 'r') as f:
         while True:
            attrs = f.readline().split()
            vals = f.readline().split()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')
            for attr,val in zip(attrs[1:], vals[1:]):
               self._data["netstat"][prefix+attr].append(val)

   def _process_proc_net_snmp(self):

      with open("/proc/net/snmp", 'r') as f:
         while True:
            attrs = f.readline().split()
            vals = f.readline().split()
            if not attrs:
               break
            prefix = attrs[0].rstrip(':')
            for attr,val in zip(attrs[1:], vals[1:]):
               self._data["snmp"][prefix+attr].append(val)

   def _process_proc_net_stat_arp_cache(self):
      with open("/proc/net/stat/arp_cache", 'r') as f:
         attr_names = f.readline().split()

         for i,l in enumerate(f.readlines()):

            cpu_label="cpu{}".format(i)
            for i,e in enumerate(l.rstrip().split()):
               self._data["arp-cache"][cpu_label][attr_names[i]].append(int(e,16))

   def _process_proc_net_stat_ndisc_cache(self):
      with open("/proc/net/stat/ndisc_cache", 'r') as f:
         attr_names = f.readline().split()

         for i,l in enumerate(f.readlines()):

            cpu_label="cpu{}".format(i)
            for i,e in enumerate(l.rstrip().split()):
               self._data["ndisc-cache"][cpu_label][attr_names[i]].append(int(e,16))

   def _process_proc_net_stat_rt_cache(self):
      """

      index is cpu label
      """
      with open("/proc/net/stat/rt_cache", 'r') as f:
         attr_names = f.readline().split()
         for i,l in enumerate(f.readlines()):

            cpu_label="cpu{}".format(i)
            for i,e in enumerate(l.rstrip().split()):
               self._data["rt-cache"][cpu_label][attr_names[i]].append(int(e,16))

   def _process_proc_net_dev(self):
      attr_names = ["rx_bytes", "rx_packets", "rx_errs", "rx_drop", "rx_fifo",
                    "rx_frame", "rx_compressed", "rx_multicast", 
                    "tx_bytes", "tx_packets", "tx_errs", "tx_drop", "tx_fifo",
                    "tx_cols", "tx_carrier", "tx_compressed"]

      active_ifs = []
      with open("/proc/net/dev", 'r') as f:

         for l in f.readlines()[2:]:
            attr_val = [e.rstrip(':') for e in l.rstrip().split()]
            index = attr_val[0] 

            if index not in self._data["net/dev"]:
               self._data["net/dev"][index] = init_rb_dict(attr_names,counter=True)

            for i,e in enumerate(attr_val[1:]):
               self._data["net/dev"][index][attr_names[i]].append(e)

            active_ifs.append(index)

      # cleanup expired ifs
      for monitored_ifs in list(self._data["net/dev"].keys()):
         if monitored_ifs not in active_ifs:
            del self._data["net/dev"][monitored_ifs]

   def _inet_ntoa(self, addr):
      """
      addr is a hex network-ordered ip address

      return numbers-and-dots string 
      """
      return str(ipaddress.ip_address(bytes(reversed(bytearray.fromhex(addr)))))

   def _process_proc_net_arp(self):
      """
      list index is ip address
      """
      attr_names = ["type", "flags", "link_addr", "mask", "dev"]

      active_entry=[]
      with open("/proc/net/arp", 'r') as f:
         for l in f.readlines()[1:]:
            split = l.rstrip().split()

            # create entry if needed
            ip_addr = split[0]
            active_entry.append(ip_addr)
            if ip_addr not in self._data["net/arp"]:
               self._data["net/arp"][ip_addr] = init_rb_dict(attr_names,type=str)

            for i,e in enumerate(split[1:]):
               self._data["net/arp"][ip_addr][attr_names[i]].append(e)

      # cleanup old entries
      for monitored_entry in list(self._data["net/arp"].keys()):
         if monitored_entry not in active_entry:
            del self._data["net/arp"][monitored_entry]


   def _process_proc_net_route(self):
      attr_names = ["if_name", "dst", "gateway", "flags", "ref_cnt", "use",
                    "metric", "mask", "mtu", "win", "irtt"]
      self._data["net/route"] = []

      with open("/proc/net/route", 'r') as f:
         for line in f.readlines()[1:]:
            entry = []
            for i,e in  enumerate(line.rstrip().split()):
               if i in [1,2,7]: # indexes of addrs
                  e=self._inet_ntoa(e)
                  
               entry.append((attr_names[i],e))
            self._data["net/route"].append(entry)


   def _open_read_append(self, path, obj):
      """
      append content of file at path to an object, if file exists

      """
      try:
         with open(path) as f:
            obj.append(f.read().rstrip())
      except:
         pass

   def _process_interfaces(self):
      """
      list interfaces and get their addresses

      index is if_name

      """

      attr_list = [
         "link_addr", "link_broadcast", "link_peer",  
         "link_gw_addr", "link_gw_if", "link_gw_default",  
         "ip4_addr", "ip4_broadcast", "ip4_netmask", "ip4_peer",
         "ip4_gw_addr", "ip4_gw_if", "ip4_gw_default",  
         "ip6_addr", "ip6_broadcast", "ip6_netmask", "ip6_peer",  
         "ip6_gw_addr", "ip6_gw_if", "ip6_gw_default",  
         
         "numa_node", "local_cpulist", "local_cpu",
         "enable", "current_link_speed", "current_link_width",
         "mtu", "tx_queue_len", "duplex", "carrier",
          "operstate",

         "carrier_down_count", "carrier_up_count",
      ]

      type_list = 31*[str] + 2*[int]
      counter_list = 31*[False] + 2*[True]

      gws = netifaces.gateways()
      active_ifs = []
      for if_name in netifaces.interfaces(): #os.listdir("/sys/class/net")
         
         # create dict if interface was never observed
         active_ifs.append(if_name)
         if if_name not in self._data["bm_ifs"]:
            self._data["bm_ifs"][if_name] = init_rb_dict(attr_list, types=type_list, 
                                                         counters=counter_list)

         # link
         addrs = netifaces.ifaddresses(if_name)
         if netifaces.AF_LINK in addrs:

            # addresses
            for item in addrs[netifaces.AF_LINK]:
               if "addr" in item:
                  self._data["bm_ifs"][if_name]["link_addr"].append(item["addr"])
               if "broadcast" in item:
                  self._data["bm_ifs"][if_name]["link_broadcast"].append(item["broadcast"])
               if "peer" in item:
                  self._data["bm_ifs"][if_name]["link_peer"].append(item["peer"])

            # gateways
            if netifaces.AF_LINK in gws:
               for item in gws[netifaces.AF_LINK]:

                  if item[1] != if_name:
                     continue
                  self._data["bm_ifs"][if_name]["link_gw_addr"].append(item[0])
                  self._data["bm_ifs"][if_name]["link_gw_if"].append(item[1])
                  self._data["bm_ifs"][if_name]["link_gw_default"].append(item[2])

         # ip4
         if netifaces.AF_INET in addrs:

            # addr
            for item in addrs[netifaces.AF_INET]:
               if "addr" in item:
                  self._data["bm_ifs"][if_name]["ip4_addr"].append(item["addr"])
               if "broadcast" in item:
                  self._data["bm_ifs"][if_name]["ip4_broadcast"].append(item["broadcast"])
               if "netmask" in item:
                  self._data["bm_ifs"][if_name]["ip4_netmask"].append(item["netmask"])
               if "peer" in item:
                  self._data["bm_ifs"][if_name]["ip4_peer"].append(item["peer"])

            # gateways
            if netifaces.AF_INET in gws:
               for item in gws[netifaces.AF_INET]:

                  if item[1] != if_name:
                     continue

                  self._data["bm_ifs"][if_name]["ip4_gw_addr"].append(item[0])
                  self._data["bm_ifs"][if_name]["ip4_gw_if"].append(item[1])
                  self._data["bm_ifs"][if_name]["ip4_gw_default"].append(item[2])

         # ip6 addr
         if netifaces.AF_INET6 in addrs:

            # addr
            for item in addrs[netifaces.AF_INET6]:
               if "addr" in item:
                  self._data["bm_ifs"][if_name]["link_addr"].append(item["addr"])
               if "broadcast" in item:
                  self._data["bm_ifs"][if_name]["ip6_broadcast"].append(item["broadcast"])
               if "netmask" in item:
                  self._data["bm_ifs"][if_name]["ip6_netmask"].append(item["netmask"])
               if "peer" in item:
                  self._data["bm_ifs"][if_name]["ip6_peer"].append(item["peer"])

            # gateways
            if netifaces.AF_INET6 in gws:
               for item in gws[netifaces.AF_INET6]:

                  if item[1] != if_name:
                     continue

                  self._data["bm_ifs"][if_name]["ip6_gw_addr"].append(item[0])
                  self._data["bm_ifs"][if_name]["ip6_gw_if"].append(item[1])
                  self._data["bm_ifs"][if_name]["ip6_gw_default"].append(tem[2])
         #
         # non-standard if attributes
         # https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-class-net
         #
         path_prefix="/sys/class/net/{}/".format(if_name)
         self._open_read_append(path_prefix+"carrier_down_count",
             self._data["bm_ifs"][if_name]["carrier_down_count"])
         self._open_read_append(path_prefix+"carrier_up_count",
             self._data["bm_ifs"][if_name]["carrier_up_count"])
         self._open_read_append(path_prefix+"device/numa_node",
             self._data["bm_ifs"][if_name]["numa_node"])
         self._open_read_append(path_prefix+"device/local_cpulist",
             self._data["bm_ifs"][if_name]["local_cpulist"])
         self._open_read_append(path_prefix+"device/local_cpu",
             self._data["bm_ifs"][if_name]["local_cpu"])
         self._open_read_append(path_prefix+"device/enable",
             self._data["bm_ifs"][if_name]["enable"])
         self._open_read_append(path_prefix+"device/current_link_speed",
             self._data["bm_ifs"][if_name]["current_link_speed"])
         self._open_read_append(path_prefix+"device/current_link_width",
             self._data["bm_ifs"][if_name]["current_link_width"])
         self._open_read_append(path_prefix+"mtu",
             self._data["bm_ifs"][if_name]["mtu"])
         self._open_read_append(path_prefix+"tx_queue_len",
             self._data["bm_ifs"][if_name]["tx_queue_len"])
         self._open_read_append(path_prefix+"duplex",
             self._data["bm_ifs"][if_name]["duplex"])
         self._open_read_append(path_prefix+"carrier",
             self._data["bm_ifs"][if_name]["carrier"])
         self._open_read_append(path_prefix+"operstate",
             self._data["bm_ifs"][if_name]["operstate"])

      # cleanup expired ifs
      for monitored_ifs in list(self._data["bm_ifs"].keys()):
         if monitored_ifs not in active_ifs:
            del self._data["bm_ifs"][monitored_ifs]

   def _process_net_settings(self):
      """
      parse network kernel parameters from /pros/sys/
      normally read through sysctl calls

      """

      with open("/proc/sys/net/core/rmem_default") as f:
         self._data["proc/sys"]["net.core.rmem_default"].append(f.read().rstrip())
      with open("/proc/sys/net/core/rmem_max") as f:
         self._data["proc/sys"]["net.core.rmem_max"].append(f.read().rstrip())
      with open("/proc/sys/net/core/wmem_default") as f:
         self._data["proc/sys"]["net.core.wmem_default"].append(f.read().rstrip())
      with open("/proc/sys/net/core/wmem_max") as f:
         self._data["proc/sys"]["net.core.wmem_max"].append(f.read().rstrip())
      with open("/proc/sys/net/core/default_qdisc") as f:
         self._data["proc/sys"]["net.core.default_qdisc"].append(f.read().rstrip())
      with open("/proc/sys/net/core/netdev_max_backlog") as f:
         self._data["proc/sys"]["net.core.netdev_max_backlog"].append(f.read().rstrip())

      attr_suffixes=["_min","_pressure", "_max"]
      page_to_bytes=4096
      with open("/proc/sys/net/ipv4/tcp_mem") as f:
         for i,e in enumerate(f.read().rstrip().split()):
            self._data["proc/sys"]["net.ipv4.tcp_mem"+attr_suffixes[i]].append(
                  int(e)*page_to_bytes)

      attr_suffixes=["_min","_default", "_max"]
      with open("/proc/sys/net/ipv4/tcp_rmem") as f:
         for i,e in enumerate(f.read().rstrip().split()):
            self._data["proc/sys"]["net.ipv4.tcp_rmem"+attr_suffixes[i]].append(e)
      with open("/proc/sys/net/ipv4/tcp_wmem") as f:
         for i,e in enumerate(f.read().rstrip().split()):
            self._data["proc/sys"]["net.ipv4.tcp_wmem"+attr_suffixes[i]].append(e)

      with open("/proc/sys/net/ipv4/tcp_congestion_control") as f:
         self._data["proc/sys"]["net.ipv4.tcp_congestion_control"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_sack") as f:
         self._data["proc/sys"]["net.ipv4.tcp_sack"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_dsack") as f:
         self._data["proc/sys"]["net.ipv4.tcp_dsack"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_fack") as f:
         self._data["proc/sys"]["net.ipv4.tcp_fack"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_syn_retries") as f:
         self._data["proc/sys"]["net.ipv4.tcp_syn_retries"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_slow_start_after_idle") as f:
         self._data["proc/sys"]["net.ipv4.tcp_slow_start_after_idle"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_retries1") as f:
         self._data["proc/sys"]["net.ipv4.tcp_retries1"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_retries2") as f:
         self._data["proc/sys"]["net.ipv4.tcp_retries2"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_mtu_probing") as f:
         self._data["proc/sys"]["net.ipv4.tcp_mtu_probing"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_max_syn_backlog") as f:
         self._data["proc/sys"]["net.ipv4.tcp_max_syn_backlog"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_base_mss") as f:
         self._data["proc/sys"]["net.ipv4.tcp_base_mss"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_min_snd_mss") as f:
         self._data["proc/sys"]["net.ipv4.tcp_min_snd_mss"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_ecn_fallback") as f:
         self._data["proc/sys"]["net.ipv4.tcp_ecn_fallback"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_ecn") as f:
         self._data["proc/sys"]["net.ipv4.tcp_ecn"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_adv_win_scale") as f:
         self._data["proc/sys"]["net.ipv4.tcp_adv_win_scale"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_window_scaling") as f:
         self._data["proc/sys"]["net.ipv4.tcp_window_scaling"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_tw_reuse") as f:
         self._data["proc/sys"]["net.ipv4.tcp_tw_reuse"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_syncookies") as f:
         self._data["proc/sys"]["net.ipv4.tcp_syncookies"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_timestamps") as f:
         self._data["proc/sys"]["net.ipv4.tcp_timestamps"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/tcp_no_metrics_save") as f:
         self._data["proc/sys"]["net.ipv4.tcp_no_metrics_save"].append(f.read().rstrip())

      with open("/proc/sys/net/ipv4/ip_forward") as f:
         self._data["proc/sys"]["net.ipv4.ip_forward"].append(f.read().rstrip())
      with open("/proc/sys/net/ipv4/ip_no_pmtu_disc") as f:
         self._data["proc/sys"]["net.ipv4.ip_no_pmtu_disc"].append(f.read().rstrip())

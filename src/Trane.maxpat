{
 "patcher": {
  "fileversion": 1,
  "appversion": {
   "major": 9,
   "minor": 0,
   "revision": 0,
   "architecture": "x64",
   "modernui": 1
  },
  "classnamespace": "box",
  "rect": [
   0.0,
   0.0,
   2550.0,
   1000.0
  ],
  "bglocked": 0,
  "openinpresentation": 1,
  "default_fontsize": 12.0,
  "default_fontface": 0,
  "gridonopen": 1,
  "gridsize": [
   15.0,
   15.0
  ],
  "boxes": [
   {
    "box": {
     "id": "obj-1",
     "maxclass": "comment",
     "text": "Träne  ·  granular freeze · grain · audio arp · huge space",
     "patching_rect": [
      30.0,
      20.0,
      510.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      8.0,
      2.0,
      596.0,
      12.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-2",
     "maxclass": "comment",
     "text": "CAPTURE",
     "patching_rect": [
      30.0,
      45.0,
      700.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      8.0,
      15.0,
      92.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-3",
     "maxclass": "newobj",
     "text": "plugin~",
     "numinlets": 0,
     "numoutlets": 2,
     "outlettype": [
      "signal",
      "signal"
     ],
     "patching_rect": [
      35.0,
      135.0,
      52.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-4",
     "maxclass": "newobj",
     "text": "buffer~ trane_capture 20000 2",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "float",
      "bang"
     ],
     "patching_rect": [
      35.0,
      245.0,
      190.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-5",
     "maxclass": "newobj",
     "text": "record~ trane_capture 2 @loop 1",
     "numinlets": 4,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      35.0,
      205.0,
      150.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-6",
     "maxclass": "newobj",
     "text": "loadbang",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      "bang"
     ],
     "patching_rect": [
      35.0,
      95.0,
      60.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-7",
     "maxclass": "message",
     "text": "1",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      105.0,
      95.0,
      32.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-9",
     "maxclass": "message",
     "text": "0",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      205.0,
      95.0,
      65.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-10",
     "maxclass": "newobj",
     "text": "groove~ trane_capture 2",
     "numinlets": 3,
     "numoutlets": 3,
     "outlettype": [
      "signal",
      "signal",
      "signal"
     ],
     "patching_rect": [
      330.0,
      205.0,
      165.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-11",
     "maxclass": "live.toggle",
     "varname": "freeze_toggle",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      330.0,
      90.0,
      22.0,
      22.0
     ],
     "presentation": 1,
     "presentation_rect": [
      8.0,
      27.0,
      22.0,
      22.0
     ],
     "parameter_enable": 1,
     "annotation": "Latch the capture: stop recording and loop the window that was just recorded.",
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_enum": [
        "off",
        "on"
       ],
       "parameter_exponent": 1.0,
       "parameter_info": "Latch the capture: stop recording and loop the window that was just recorded.",
       "parameter_initial": [
        0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Freeze",
       "parameter_mmax": 1.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Freeze",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 2,
       "parameter_units": ""
      }
     }
    }
   },
   {
    "box": {
     "id": "obj-12",
     "maxclass": "comment",
     "text": "FREEZE",
     "patching_rect": [
      360.0,
      92.0,
      120.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      33.0,
      32.0,
      62.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-13",
     "maxclass": "newobj",
     "text": "sel 1",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "bang",
      "bang"
     ],
     "patching_rect": [
      330.0,
      130.0,
      42.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-14",
     "maxclass": "message",
     "text": "startloop",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      382.0,
      130.0,
      62.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-15",
     "maxclass": "newobj",
     "text": "+ 1",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "int"
     ],
     "patching_rect": [
      455.0,
      130.0,
      35.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-16",
     "maxclass": "live.toggle",
     "varname": "reverse_toggle",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      530.0,
      90.0,
      22.0,
      22.0
     ],
     "presentation": 1,
     "presentation_rect": [
      104.0,
      27.0,
      22.0,
      22.0
     ],
     "parameter_enable": 1,
     "annotation": "Play the frozen window backwards.",
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_enum": [
        "off",
        "on"
       ],
       "parameter_exponent": 1.0,
       "parameter_info": "Play the frozen window backwards.",
       "parameter_initial": [
        0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Reverse",
       "parameter_mmax": 1.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Reverse",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 2,
       "parameter_units": ""
      }
     }
    }
   },
   {
    "box": {
     "id": "obj-17",
     "maxclass": "comment",
     "text": "REVERSE",
     "patching_rect": [
      560.0,
      92.0,
      70.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      129.0,
      32.0,
      62.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-18",
     "maxclass": "newobj",
     "text": "expr 1 - ($i1 * 2)",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      "int"
     ],
     "patching_rect": [
      530.0,
      130.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-19",
     "maxclass": "newobj",
     "text": "sig~ 1.",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      660.0,
      130.0,
      50.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-20",
     "maxclass": "live.dial",
     "varname": "loop_length_ms",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      740.0,
      90.0,
      42.0,
      42.0
     ],
     "presentation": 1,
     "presentation_rect": [
      8.0,
      52.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Length of the frozen loop window, in milliseconds.",
       "parameter_initial": [
        100.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Loop Length",
       "parameter_mmax": 500.0,
       "parameter_mmin": 5.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Loop",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 2
      }
     },
     "annotation": "Length of the frozen loop window, in milliseconds."
    }
   },
   {
    "box": {
     "id": "obj-21",
     "maxclass": "comment",
     "text": "LOOP ms",
     "patching_rect": [
      790.0,
      100.0,
      385.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      8.0,
      91.0,
      46.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-22",
     "maxclass": "newobj",
     "text": "selector~ 2",
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      550.0,
      300.0,
      75.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-23",
     "maxclass": "newobj",
     "text": "selector~ 2",
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      650.0,
      300.0,
      75.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-24",
     "maxclass": "live.tab",
     "varname": "sound_mode",
     "numinlets": 1,
     "numoutlets": 3,
     "outlettype": [
      "",
      "",
      "float"
     ],
     "patching_rect": [
      800.0,
      90.0,
      95.0,
      24.0
     ],
     "presentation": 1,
     "presentation_rect": [
      200.0,
      27.0,
      90.0,
      22.0
     ],
     "parameter_enable": 1,
     "annotation": "Clear: clean granular. Ruin: hard-clipped, deconstructed.",
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_enum": [
        "Clear",
        "Ruin"
       ],
       "parameter_exponent": 1.0,
       "parameter_info": "Clear: clean granular. Ruin: hard-clipped, deconstructed.",
       "parameter_initial": [
        0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Sound Mode",
       "parameter_mmax": 1.0,
       "parameter_mmin": 0.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Mode",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 2,
       "parameter_units": "",
       "parameter_unitstyle": 9
      }
     }
    }
   },
   {
    "box": {
     "id": "obj-25",
     "maxclass": "comment",
     "text": "MODE",
     "patching_rect": [
      905.0,
      92.0,
      95.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      293.0,
      32.0,
      40.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-26",
     "maxclass": "newobj",
     "text": "+ 1",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "int"
     ],
     "patching_rect": [
      800.0,
      135.0,
      35.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-27",
     "maxclass": "newobj",
     "text": "*~ 3.",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      550.0,
      350.0,
      45.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-28",
     "maxclass": "newobj",
     "text": "*~ 3.",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      650.0,
      350.0,
      45.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-29",
     "maxclass": "newobj",
     "text": "clip~ -0.45 0.45",
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      550.0,
      390.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-30",
     "maxclass": "newobj",
     "text": "clip~ -0.45 0.45",
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      690.0,
      390.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-31",
     "maxclass": "newobj",
     "text": "selector~ 2",
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      550.0,
      445.0,
      75.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-32",
     "maxclass": "newobj",
     "text": "selector~ 2",
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      690.0,
      445.0,
      75.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-33",
     "maxclass": "newobj",
     "text": "limi~",
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      550.0,
      500.0,
      40.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-34",
     "maxclass": "newobj",
     "text": "limi~",
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      690.0,
      500.0,
      40.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-35",
     "maxclass": "newobj",
     "text": "plugout~",
     "numinlets": 2,
     "numoutlets": 0,
     "outlettype": [],
     "patching_rect": [
      620.0,
      555.0,
      60.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-36",
     "maxclass": "comment",
     "text": "Safety: per-channel limiter before Live output",
     "patching_rect": [
      760.0,
      505.0,
      260.0,
      20.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-37",
     "maxclass": "comment",
     "text": "ARP",
     "patching_rect": [
      30.0,
      635.0,
      1030.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      466.0,
      32.0,
      34.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-38",
     "maxclass": "comment",
     "text": "Freeze: record~ runs in loop mode inside [0, loop_length_ms], so the buffer always holds the most recent window. Freeze stops the recording and loops that window in groove~.",
     "patching_rect": [
      30.0,
      665.0,
      1100.0,
      20.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-40",
     "maxclass": "message",
     "text": "0",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      995.0,
      135.0,
      30.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-45",
     "maxclass": "newobj",
     "text": "prepend setloop 0",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      "list"
     ],
     "patching_rect": [
      420.0,
      325.0,
      95.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-47",
     "maxclass": "message",
     "text": "100.",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      705.0,
      165.0,
      38.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-48",
     "maxclass": "comment",
     "text": "Rolling capture: record~ loops inside [0, loop_length_ms].",
     "patching_rect": [
      30.0,
      600.0,
      1000.0,
      20.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-49",
     "maxclass": "comment",
     "text": "GRAIN",
     "patching_rect": [
      30.0,
      665.0,
      800.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      375.0,
      32.0,
      46.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-50",
     "maxclass": "live.toggle",
     "varname": "grain_toggle",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      30.0,
      470.0,
      22.0,
      22.0
     ],
     "presentation": 1,
     "presentation_rect": [
      350.0,
      27.0,
      22.0,
      22.0
     ],
     "parameter_enable": 1,
     "annotation": "Enable the granular voice pool.",
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_enum": [
        "off",
        "on"
       ],
       "parameter_exponent": 1.0,
       "parameter_info": "Enable the granular voice pool.",
       "parameter_initial": [
        0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Grain Enable",
       "parameter_mmax": 1.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Grain",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 2,
       "parameter_units": ""
      }
     }
    }
   },
   {
    "box": {
     "id": "obj-51",
     "maxclass": "comment",
     "text": "GRAIN",
     "patching_rect": [
      60.0,
      472.0,
      55.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      104.0,
      15.0,
      236.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-52",
     "maxclass": "live.dial",
     "varname": "grain_size_ms",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      130.0,
      455.0,
      42.0,
      42.0
     ],
     "presentation": 1,
     "presentation_rect": [
      104.0,
      52.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Length of each grain, in milliseconds.",
       "parameter_initial": [
        100.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Grain Size",
       "parameter_mmax": 500.0,
       "parameter_mmin": 5.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Size",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 2
      }
     },
     "annotation": "Length of each grain, in milliseconds."
    }
   },
   {
    "box": {
     "id": "obj-53",
     "maxclass": "comment",
     "text": "SIZE",
     "patching_rect": [
      130.0,
      505.0,
      40.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      104.0,
      91.0,
      40.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-54",
     "maxclass": "live.dial",
     "varname": "grain_density",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      205.0,
      455.0,
      42.0,
      42.0
     ],
     "presentation": 1,
     "presentation_rect": [
      152.0,
      52.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Grains per second.",
       "parameter_initial": [
        8.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Grain Density",
       "parameter_mmax": 20.0,
       "parameter_mmin": 1.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Density",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 3
      }
     },
     "annotation": "Grains per second."
    }
   },
   {
    "box": {
     "id": "obj-55",
     "maxclass": "comment",
     "text": "DENSITY",
     "patching_rect": [
      195.0,
      505.0,
      60.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      152.0,
      91.0,
      46.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-56",
     "maxclass": "live.dial",
     "varname": "grain_position",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      285.0,
      455.0,
      42.0,
      42.0
     ],
     "presentation": 1,
     "presentation_rect": [
      200.0,
      52.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Read position inside the capture, 0 = start, 1 = end.",
       "parameter_initial": [
        0.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Grain Position",
       "parameter_mmax": 1.0,
       "parameter_mmin": 0.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Position",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 1
      }
     },
     "annotation": "Read position inside the capture, 0 = start, 1 = end."
    }
   },
   {
    "box": {
     "id": "obj-57",
     "maxclass": "comment",
     "text": "POSITION",
     "patching_rect": [
      275.0,
      505.0,
      65.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      200.0,
      91.0,
      46.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-58",
     "maxclass": "live.dial",
     "varname": "grain_spray",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      365.0,
      455.0,
      42.0,
      42.0
     ],
     "presentation": 1,
     "presentation_rect": [
      248.0,
      52.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Random spread around the read position.",
       "parameter_initial": [
        0.1
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Grain Spray",
       "parameter_mmax": 1.0,
       "parameter_mmin": 0.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Spray",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 1
      }
     },
     "annotation": "Random spread around the read position."
    }
   },
   {
    "box": {
     "id": "obj-59",
     "maxclass": "comment",
     "text": "SPRAY",
     "patching_rect": [
      360.0,
      505.0,
      50.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      248.0,
      91.0,
      40.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-60",
     "maxclass": "newobj",
     "text": "expr 1000. / max(1., $f1)",
     "patching_rect": [
      205.0,
      540.0,
      150.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-61",
     "maxclass": "newobj",
     "text": "metro 166",
     "patching_rect": [
      35.0,
      540.0,
      65.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "bang"
     ]
    }
   },
   {
    "box": {
     "id": "obj-62",
     "maxclass": "newobj",
     "text": "sel 1",
     "patching_rect": [
      35.0,
      505.0,
      42.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "bang",
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-63",
     "maxclass": "message",
     "text": "1",
     "patching_rect": [
      90.0,
      505.0,
      30.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-64",
     "maxclass": "message",
     "text": "0",
     "patching_rect": [
      125.0,
      505.0,
      30.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-65",
     "maxclass": "newobj",
     "text": "t b b",
     "patching_rect": [
      35.0,
      580.0,
      40.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "bang",
      "bang"
     ]
    }
   },
   {
    "box": {
     "id": "obj-66",
     "maxclass": "newobj",
     "text": "random 6",
     "patching_rect": [
      90.0,
      580.0,
      60.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "int"
     ]
    }
   },
   {
    "box": {
     "id": "obj-67",
     "maxclass": "newobj",
     "text": "+ 1",
     "patching_rect": [
      160.0,
      580.0,
      35.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-68",
     "maxclass": "newobj",
     "text": "sprintf target %ld",
     "patching_rect": [
      205.0,
      580.0,
      105.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-69",
     "maxclass": "newobj",
     "text": "random 10000",
     "patching_rect": [
      330.0,
      580.0,
      88.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "int"
     ]
    }
   },
   {
    "box": {
     "id": "obj-70",
     "maxclass": "newobj",
     "text": "/ 10000.",
     "patching_rect": [
      430.0,
      580.0,
      60.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-71",
     "maxclass": "newobj",
     "text": "expr max(0., min(19000., ($f1 * 19000.) + (($f2 - .5) * $f3 * 8000.)))",
     "patching_rect": [
      500.0,
      580.0,
      450.0,
      22.0
     ],
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-72",
     "maxclass": "newobj",
     "text": "pack f f f",
     "patching_rect": [
      700.0,
      540.0,
      65.0,
      22.0
     ],
     "numinlets": 3,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-73",
     "maxclass": "newobj",
     "text": "prepend trigger",
     "patching_rect": [
      775.0,
      540.0,
      100.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-74",
     "maxclass": "newobj",
     "text": "poly~ TraneGrainVoice 6",
     "patching_rect": [
      885.0,
      540.0,
      155.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "signal",
      "signal"
     ]
    }
   },
   {
    "box": {
     "id": "obj-75",
     "maxclass": "newobj",
     "text": "*~ 0.4",
     "patching_rect": [
      885.0,
      580.0,
      48.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ]
    }
   },
   {
    "box": {
     "id": "obj-76",
     "maxclass": "newobj",
     "text": "*~ 0.4",
     "patching_rect": [
      950.0,
      580.0,
      48.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ]
    }
   },
   {
    "box": {
     "id": "obj-77",
     "maxclass": "newobj",
     "text": "+~",
     "patching_rect": [
      550.0,
      475.0,
      35.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ]
    }
   },
   {
    "box": {
     "id": "obj-78",
     "maxclass": "newobj",
     "text": "+~",
     "patching_rect": [
      690.0,
      475.0,
      35.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ]
    }
   },
   {
    "box": {
     "id": "obj-79",
     "maxclass": "message",
     "text": "1.",
     "patching_rect": [
      650.0,
      540.0,
      30.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-80",
     "maxclass": "live.dial",
     "varname": "grain_rate",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      450.0,
      455.0,
      42.0,
      42.0
     ],
     "presentation": 1,
     "presentation_rect": [
      296.0,
      52.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Grain playback rate. 1 = original speed.",
       "parameter_initial": [
        1.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Grain Rate",
       "parameter_mmax": 2.0,
       "parameter_mmin": 0.5,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Rate",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 1
      }
     },
     "annotation": "Grain playback rate. 1 = original speed."
    }
   },
   {
    "box": {
     "id": "obj-81",
     "maxclass": "comment",
     "text": "RATE",
     "patching_rect": [
      445.0,
      505.0,
      45.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      296.0,
      91.0,
      40.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-82",
     "maxclass": "newobj",
     "text": "* 1.",
     "patching_rect": [
      610.0,
      540.0,
      35.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-84",
     "maxclass": "live.toggle",
     "varname": "arp_toggle",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      30.0,
      705.0,
      22.0,
      22.0
     ],
     "presentation": 1,
     "presentation_rect": [
      440.0,
      27.0,
      22.0,
      22.0
     ],
     "parameter_enable": 1,
     "annotation": "Start the audio arpeggiator. Steps retrigger the grain voices.",
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_enum": [
        "off",
        "on"
       ],
       "parameter_exponent": 1.0,
       "parameter_info": "Start the audio arpeggiator. Steps retrigger the grain voices.",
       "parameter_initial": [
        0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Arpeggiator Enable",
       "parameter_mmax": 1.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Arp",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 2,
       "parameter_units": ""
      }
     }
    }
   },
   {
    "box": {
     "id": "obj-85",
     "maxclass": "comment",
     "text": "ARP",
     "patching_rect": [
      60.0,
      707.0,
      75.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      440.0,
      15.0,
      150.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-86",
     "maxclass": "live.menu",
     "varname": "arp_rate",
     "numinlets": 1,
     "numoutlets": 3,
     "outlettype": [
      "",
      "",
      "float"
     ],
     "patching_rect": [
      150.0,
      700.0,
      80.0,
      22.0
     ],
     "presentation": 1,
     "presentation_rect": [
      506.0,
      27.0,
      78.0,
      22.0
     ],
     "parameter_enable": 1,
     "annotation": "Step rate of the arpeggiator, relative to Live's tempo.",
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_enum": [
        "1/16",
        "1/8",
        "1/4",
        "1/2"
       ],
       "parameter_exponent": 1.0,
       "parameter_info": "Step rate of the arpeggiator, relative to Live's tempo.",
       "parameter_initial": [
        0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Arp Rate",
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Rate",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 2,
       "parameter_units": ""
      }
     }
    }
   },
   {
    "box": {
     "id": "obj-88",
     "maxclass": "newobj",
     "text": "sel 0 1 2 3",
     "patching_rect": [
      150.0,
      735.0,
      90.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 5,
     "outlettype": [
      "bang",
      "",
      "",
      "",
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-89",
     "maxclass": "message",
     "text": "16n",
     "patching_rect": [
      250.0,
      735.0,
      35.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-90",
     "maxclass": "message",
     "text": "8n",
     "patching_rect": [
      292.0,
      735.0,
      35.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-91",
     "maxclass": "message",
     "text": "4n",
     "patching_rect": [
      334.0,
      735.0,
      35.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-92",
     "maxclass": "message",
     "text": "2n",
     "patching_rect": [
      376.0,
      735.0,
      42.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-93",
     "maxclass": "newobj",
     "text": "metro 16n",
     "patching_rect": [
      430.0,
      705.0,
      65.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "bang"
     ]
    }
   },
   {
    "box": {
     "id": "obj-94",
     "maxclass": "live.dial",
     "varname": "arp_probability",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      515.0,
      690.0,
      42.0,
      42.0
     ],
     "presentation": 1,
     "presentation_rect": [
      506.0,
      52.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Chance that a step actually fires, in percent.",
       "parameter_initial": [
        100.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Arp Probability",
       "parameter_mmax": 100.0,
       "parameter_mmin": 0.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Prob",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 5
      }
     },
     "annotation": "Chance that a step actually fires, in percent."
    }
   },
   {
    "box": {
     "id": "obj-95",
     "maxclass": "comment",
     "text": "PROB",
     "patching_rect": [
      510.0,
      740.0,
      45.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      506.0,
      91.0,
      40.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-96",
     "maxclass": "live.dial",
     "varname": "arp_steps",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      585.0,
      690.0,
      42.0,
      42.0
     ],
     "presentation": 1,
     "presentation_rect": [
      554.0,
      52.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Number of steps in the arpeggio cycle.",
       "parameter_initial": [
        8.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Arp Steps",
       "parameter_mmax": 16.0,
       "parameter_mmin": 1.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Steps",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 1,
       "parameter_units": "",
       "parameter_unitstyle": 0
      }
     },
     "annotation": "Number of steps in the arpeggio cycle."
    }
   },
   {
    "box": {
     "id": "obj-97",
     "maxclass": "comment",
     "text": "STEPS",
     "patching_rect": [
      580.0,
      740.0,
      50.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      554.0,
      91.0,
      40.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-98",
     "maxclass": "newobj",
     "text": "random 100",
     "patching_rect": [
      650.0,
      705.0,
      88.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "int"
     ]
    }
   },
   {
    "box": {
     "id": "obj-99",
     "maxclass": "newobj",
     "text": "< 100.",
     "patching_rect": [
      750.0,
      705.0,
      55.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "int"
     ]
    }
   },
   {
    "box": {
     "id": "obj-100",
     "maxclass": "newobj",
     "text": "sel 1",
     "patching_rect": [
      815.0,
      705.0,
      42.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "bang",
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-101",
     "maxclass": "newobj",
     "text": "counter 1 16",
     "patching_rect": [
      865.0,
      705.0,
      80.0,
      22.0
     ],
     "numinlets": 3,
     "numoutlets": 3,
     "outlettype": [
      "int",
      "int",
      "int"
     ]
    }
   },
   {
    "box": {
     "id": "obj-102",
     "maxclass": "newobj",
     "text": "expr 0.5 + (($i1 - 1) / 15.)",
     "patching_rect": [
      955.0,
      705.0,
      190.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-103",
     "maxclass": "newobj",
     "text": "*",
     "patching_rect": [
      955.0,
      740.0,
      30.0,
      22.0
     ],
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-104",
     "maxclass": "comment",
     "text": "Audio ARP: tempo-relative steps (16n/8n/4n/2n) retrigger the grain voices.",
     "patching_rect": [
      30.0,
      765.0,
      1050.0,
      20.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-105",
     "maxclass": "comment",
     "text": "HUGE SPACE",
     "patching_rect": [
      900.0,
      55.0,
      160.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      8.0,
      104.0,
      110.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-106",
     "maxclass": "comment",
     "text": "8s+ feedback plate",
     "patching_rect": [
      900.0,
      77.0,
      180.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      122.0,
      104.0,
      140.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-107",
     "maxclass": "live.dial",
     "varname": "verb_mix",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      900.0,
      125.0,
      45.0,
      45.0
     ],
     "presentation": 1,
     "presentation_rect": [
      8.0,
      116.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Wet/dry blend of the Huge Space plate.",
       "parameter_initial": [
        55.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Space Mix",
       "parameter_mmax": 100.0,
       "parameter_mmin": 0.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Mix",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 5
      }
     },
     "annotation": "Wet/dry blend of the Huge Space plate."
    }
   },
   {
    "box": {
     "id": "obj-108",
     "maxclass": "comment",
     "text": "MIX",
     "patching_rect": [
      900.0,
      175.0,
      45.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      8.0,
      155.0,
      40.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-109",
     "maxclass": "live.dial",
     "varname": "verb_size",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      962.0,
      125.0,
      45.0,
      45.0
     ],
     "presentation": 1,
     "presentation_rect": [
      76.0,
      116.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Size of the plate. Higher = longer early reflections.",
       "parameter_initial": [
        70.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Space Size",
       "parameter_mmax": 100.0,
       "parameter_mmin": 0.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Space",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 5
      }
     },
     "annotation": "Size of the plate. Higher = longer early reflections."
    }
   },
   {
    "box": {
     "id": "obj-110",
     "maxclass": "comment",
     "text": "SPACE",
     "patching_rect": [
      958.0,
      175.0,
      58.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      76.0,
      155.0,
      46.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-111",
     "maxclass": "live.dial",
     "varname": "verb_decay",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      1024.0,
      125.0,
      45.0,
      45.0
     ],
     "presentation": 1,
     "presentation_rect": [
      144.0,
      116.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Decay time. At the top this tail runs 8 s and beyond.",
       "parameter_initial": [
        80.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Space Decay",
       "parameter_mmax": 100.0,
       "parameter_mmin": 0.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Tail",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 5
      }
     },
     "annotation": "Decay time. At the top this tail runs 8 s and beyond."
    }
   },
   {
    "box": {
     "id": "obj-112",
     "maxclass": "comment",
     "text": "TAIL",
     "patching_rect": [
      1028.0,
      175.0,
      45.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      144.0,
      155.0,
      40.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-113",
     "maxclass": "live.dial",
     "varname": "verb_damping",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      900.0,
      228.0,
      45.0,
      45.0
     ],
     "presentation": 1,
     "presentation_rect": [
      212.0,
      116.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "High-frequency damping inside the plate.",
       "parameter_initial": [
        40.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Space Damping",
       "parameter_mmax": 100.0,
       "parameter_mmin": 0.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Damp",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 5
      }
     },
     "annotation": "High-frequency damping inside the plate."
    }
   },
   {
    "box": {
     "id": "obj-114",
     "maxclass": "comment",
     "text": "DAMP",
     "patching_rect": [
      900.0,
      278.0,
      45.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      212.0,
      155.0,
      44.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-115",
     "maxclass": "live.dial",
     "varname": "verb_diffusion",
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      "float"
     ],
     "patching_rect": [
      962.0,
      228.0,
      45.0,
      45.0
     ],
     "presentation": 1,
     "presentation_rect": [
      280.0,
      116.0,
      38.0,
      38.0
     ],
     "parameter_enable": 1,
     "saved_attribute_attributes": {
      "valueof": {
       "parameter_annotation_name": "",
       "parameter_exponent": 1.0,
       "parameter_info": "Diffusion of the plate network. Higher = smoother tail.",
       "parameter_initial": [
        70.0
       ],
       "parameter_initial_enable": 1,
       "parameter_invisible": 0,
       "parameter_linknames": 1,
       "parameter_longname": "Space Diffusion",
       "parameter_mmax": 100.0,
       "parameter_mmin": 0.0,
       "parameter_modmax": 127.0,
       "parameter_modmin": 0.0,
       "parameter_modmode": 0,
       "parameter_order": 0,
       "parameter_shortname": "Diffuse",
       "parameter_speedlim": 0,
       "parameter_steps": 0,
       "parameter_type": 0,
       "parameter_units": "",
       "parameter_unitstyle": 5
      }
     },
     "annotation": "Diffusion of the plate network. Higher = smoother tail."
    }
   },
   {
    "box": {
     "id": "obj-116",
     "maxclass": "comment",
     "text": "DIFFUSE",
     "patching_rect": [
      952.0,
      278.0,
      70.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      280.0,
      155.0,
      56.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-117",
     "maxclass": "newobj",
     "text": "+~",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      920.0,
      500.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-118",
     "maxclass": "newobj",
     "text": "*~ 0.5",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      1040.0,
      500.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-119",
     "maxclass": "newobj",
     "text": "TraneHugeVerb",
     "numinlets": 5,
     "numoutlets": 2,
     "outlettype": [
      "signal",
      "signal"
     ],
     "patching_rect": [
      1040.0,
      550.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-120",
     "maxclass": "newobj",
     "text": "* 0.01",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "float"
     ],
     "patching_rect": [
      930.0,
      410.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-121",
     "maxclass": "newobj",
     "text": "* 1.27",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "float"
     ],
     "patching_rect": [
      1020.0,
      410.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-122",
     "maxclass": "newobj",
     "text": "* 1.27",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "float"
     ],
     "patching_rect": [
      1100.0,
      410.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-123",
     "maxclass": "newobj",
     "text": "* 1.27",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "float"
     ],
     "patching_rect": [
      1180.0,
      410.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-124",
     "maxclass": "newobj",
     "text": "* 1.27",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "float"
     ],
     "patching_rect": [
      1260.0,
      410.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-125",
     "maxclass": "newobj",
     "text": "*~",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      920.0,
      610.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-126",
     "maxclass": "newobj",
     "text": "*~",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      1010.0,
      610.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-127",
     "maxclass": "newobj",
     "text": "+~",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      920.0,
      670.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-128",
     "maxclass": "newobj",
     "text": "+~",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      1010.0,
      670.0,
      120.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-129",
     "maxclass": "comment",
     "text": "Huge Space: mono fold-down → 8s+ plate network → stereo wet return. The dry path stays untouched.",
     "patching_rect": [
      1800.0,
      775.0,
      680.0,
      20.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-130",
     "maxclass": "comment",
     "text": "RATE",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      40.0,
      940.0,
      90.0,
      20.0
     ],
     "presentation": 1,
     "presentation_rect": [
      588.0,
      32.0,
      42.0,
      11.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-132",
     "maxclass": "message",
     "text": "1",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      ""
     ],
     "patching_rect": [
      40.0,
      940.0,
      90.0,
      20.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-133",
     "maxclass": "newobj",
     "text": "expr 1. - $f1",
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      "float"
     ],
     "patching_rect": [
      2400.0,
      560.0,
      110.0,
      20.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-134",
     "maxclass": "newobj",
     "text": "*~",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      2400.0,
      590.0,
      36.0,
      20.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-135",
     "maxclass": "newobj",
     "text": "*~",
     "numinlets": 2,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ],
     "patching_rect": [
      2400.0,
      620.0,
      36.0,
      20.0
     ]
    }
   }
  ],
  "lines": [
   {
    "patchline": {
     "source": [
      "obj-6",
      0
     ],
     "destination": [
      "obj-7",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      0
     ],
     "destination": [
      "obj-47",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      0
     ],
     "destination": [
      "obj-40",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-7",
      0
     ],
     "destination": [
      "obj-5",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-40",
      0
     ],
     "destination": [
      "obj-24",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-40",
      0
     ],
     "destination": [
      "obj-15",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-40",
      0
     ],
     "destination": [
      "obj-16",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-3",
      0
     ],
     "destination": [
      "obj-5",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-3",
      1
     ],
     "destination": [
      "obj-5",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-11",
      0
     ],
     "destination": [
      "obj-13",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-11",
      0
     ],
     "destination": [
      "obj-15",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-13",
      0
     ],
     "destination": [
      "obj-9",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-14",
      0
     ],
     "destination": [
      "obj-10",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-47",
      0
     ],
     "destination": [
      "obj-20",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-16",
      0
     ],
     "destination": [
      "obj-18",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-18",
      0
     ],
     "destination": [
      "obj-19",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-19",
      0
     ],
     "destination": [
      "obj-10",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-15",
      0
     ],
     "destination": [
      "obj-22",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-15",
      0
     ],
     "destination": [
      "obj-23",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-3",
      0
     ],
     "destination": [
      "obj-22",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-3",
      1
     ],
     "destination": [
      "obj-23",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-10",
      0
     ],
     "destination": [
      "obj-22",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-10",
      1
     ],
     "destination": [
      "obj-23",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-24",
      0
     ],
     "destination": [
      "obj-26",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-26",
      0
     ],
     "destination": [
      "obj-31",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-26",
      0
     ],
     "destination": [
      "obj-32",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-22",
      0
     ],
     "destination": [
      "obj-27",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-23",
      0
     ],
     "destination": [
      "obj-28",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-22",
      0
     ],
     "destination": [
      "obj-31",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-23",
      0
     ],
     "destination": [
      "obj-32",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-27",
      0
     ],
     "destination": [
      "obj-29",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-28",
      0
     ],
     "destination": [
      "obj-30",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-29",
      0
     ],
     "destination": [
      "obj-31",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-30",
      0
     ],
     "destination": [
      "obj-32",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-31",
      0
     ],
     "destination": [
      "obj-77",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-32",
      0
     ],
     "destination": [
      "obj-78",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-75",
      0
     ],
     "destination": [
      "obj-77",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-76",
      0
     ],
     "destination": [
      "obj-78",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-33",
      0
     ],
     "destination": [
      "obj-35",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-34",
      0
     ],
     "destination": [
      "obj-35",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-40",
      0
     ],
     "destination": [
      "obj-50",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-47",
      0
     ],
     "destination": [
      "obj-52",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-50",
      0
     ],
     "destination": [
      "obj-62",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-62",
      0
     ],
     "destination": [
      "obj-63",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-62",
      1
     ],
     "destination": [
      "obj-64",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-63",
      0
     ],
     "destination": [
      "obj-61",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-64",
      0
     ],
     "destination": [
      "obj-61",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-54",
      0
     ],
     "destination": [
      "obj-60",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-60",
      0
     ],
     "destination": [
      "obj-61",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-61",
      0
     ],
     "destination": [
      "obj-65",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-65",
      1
     ],
     "destination": [
      "obj-66",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-66",
      0
     ],
     "destination": [
      "obj-67",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-67",
      0
     ],
     "destination": [
      "obj-68",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-68",
      0
     ],
     "destination": [
      "obj-74",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-65",
      0
     ],
     "destination": [
      "obj-69",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-69",
      0
     ],
     "destination": [
      "obj-70",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-56",
      0
     ],
     "destination": [
      "obj-71",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-70",
      0
     ],
     "destination": [
      "obj-71",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-58",
      0
     ],
     "destination": [
      "obj-71",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-71",
      0
     ],
     "destination": [
      "obj-72",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-52",
      0
     ],
     "destination": [
      "obj-72",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-82",
      0
     ],
     "destination": [
      "obj-72",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-72",
      0
     ],
     "destination": [
      "obj-73",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-73",
      0
     ],
     "destination": [
      "obj-74",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-74",
      0
     ],
     "destination": [
      "obj-75",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-74",
      1
     ],
     "destination": [
      "obj-76",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      0
     ],
     "destination": [
      "obj-79",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-79",
      0
     ],
     "destination": [
      "obj-80",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-18",
      0
     ],
     "destination": [
      "obj-82",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-84",
      0
     ],
     "destination": [
      "obj-93",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-86",
      0
     ],
     "destination": [
      "obj-88",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-88",
      0
     ],
     "destination": [
      "obj-89",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-88",
      1
     ],
     "destination": [
      "obj-90",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-88",
      2
     ],
     "destination": [
      "obj-91",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-88",
      3
     ],
     "destination": [
      "obj-92",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-89",
      0
     ],
     "destination": [
      "obj-93",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-90",
      0
     ],
     "destination": [
      "obj-93",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-91",
      0
     ],
     "destination": [
      "obj-93",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-92",
      0
     ],
     "destination": [
      "obj-93",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-93",
      0
     ],
     "destination": [
      "obj-98",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-98",
      0
     ],
     "destination": [
      "obj-99",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-94",
      0
     ],
     "destination": [
      "obj-99",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-99",
      0
     ],
     "destination": [
      "obj-100",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-100",
      0
     ],
     "destination": [
      "obj-65",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-100",
      0
     ],
     "destination": [
      "obj-101",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-96",
      0
     ],
     "destination": [
      "obj-101",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-101",
      0
     ],
     "destination": [
      "obj-102",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-102",
      0
     ],
     "destination": [
      "obj-103",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-80",
      0
     ],
     "destination": [
      "obj-103",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-103",
      0
     ],
     "destination": [
      "obj-82",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-77",
      0
     ],
     "destination": [
      "obj-117",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-78",
      0
     ],
     "destination": [
      "obj-117",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-117",
      0
     ],
     "destination": [
      "obj-118",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-118",
      0
     ],
     "destination": [
      "obj-119",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-107",
      0
     ],
     "destination": [
      "obj-120",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-120",
      0
     ],
     "destination": [
      "obj-125",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-120",
      0
     ],
     "destination": [
      "obj-126",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-109",
      0
     ],
     "destination": [
      "obj-121",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-121",
      0
     ],
     "destination": [
      "obj-119",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-111",
      0
     ],
     "destination": [
      "obj-122",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-122",
      0
     ],
     "destination": [
      "obj-119",
      2
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-113",
      0
     ],
     "destination": [
      "obj-123",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-123",
      0
     ],
     "destination": [
      "obj-119",
      3
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-115",
      0
     ],
     "destination": [
      "obj-124",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-124",
      0
     ],
     "destination": [
      "obj-119",
      4
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-119",
      0
     ],
     "destination": [
      "obj-125",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-119",
      1
     ],
     "destination": [
      "obj-126",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-125",
      0
     ],
     "destination": [
      "obj-127",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-126",
      0
     ],
     "destination": [
      "obj-128",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-127",
      0
     ],
     "destination": [
      "obj-33",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-128",
      0
     ],
     "destination": [
      "obj-34",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-20",
      0
     ],
     "destination": [
      "obj-5",
      3
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-20",
      0
     ],
     "destination": [
      "obj-45",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-45",
      0
     ],
     "destination": [
      "obj-10",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-9",
      0
     ],
     "destination": [
      "obj-5",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-13",
      0
     ],
     "destination": [
      "obj-14",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-13",
      1
     ],
     "destination": [
      "obj-132",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-132",
      0
     ],
     "destination": [
      "obj-5",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-77",
      0
     ],
     "destination": [
      "obj-134",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-134",
      0
     ],
     "destination": [
      "obj-127",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-78",
      0
     ],
     "destination": [
      "obj-135",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-135",
      0
     ],
     "destination": [
      "obj-128",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-120",
      0
     ],
     "destination": [
      "obj-133",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-133",
      0
     ],
     "destination": [
      "obj-134",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-133",
      0
     ],
     "destination": [
      "obj-135",
      1
     ]
    }
   }
  ],
  "openrect": [
   0.0,
   0.0,
   650.0,
   169.0
  ],
  "devicewidth": 650.0
 }
}
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
   100.0,
   100.0,
   820.0,
   500.0
  ],
  "boxes": [
   {
    "box": {
     "id": "obj-1",
     "maxclass": "inlet",
     "comment": "trigger <start-ms> <duration-ms> <rate>",
     "patching_rect": [
      30.0,
      35.0,
      25.0,
      25.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-2",
     "maxclass": "newobj",
     "text": "route trigger",
     "patching_rect": [
      30.0,
      80.0,
      75.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "",
      ""
     ]
    }
   },
   {
    "box": {
     "id": "obj-3",
     "maxclass": "newobj",
     "text": "unpack f f f",
     "patching_rect": [
      30.0,
      120.0,
      85.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 3,
     "outlettype": [
      "float",
      "float",
      "float"
     ]
    }
   },
   {
    "box": {
     "id": "obj-4",
     "maxclass": "newobj",
     "text": "t f f",
     "patching_rect": [
      30.0,
      160.0,
      40.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "float",
      "float"
     ]
    }
   },
   {
    "box": {
     "id": "obj-5",
     "maxclass": "newobj",
     "text": "+ 100.",
     "patching_rect": [
      90.0,
      160.0,
      50.0,
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
     "id": "obj-6",
     "maxclass": "newobj",
     "text": "pack f f",
     "patching_rect": [
      160.0,
      160.0,
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
     "id": "obj-7",
     "maxclass": "newobj",
     "text": "prepend setloop",
     "patching_rect": [
      240.0,
      160.0,
      95.0,
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
     "id": "obj-8",
     "maxclass": "newobj",
     "text": "t b l",
     "patching_rect": [
      355.0,
      160.0,
      40.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "bang",
      "list"
     ]
    }
   },
   {
    "box": {
     "id": "obj-9",
     "maxclass": "message",
     "text": "startloop",
     "patching_rect": [
      415.0,
      160.0,
      62.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-10",
     "maxclass": "newobj",
     "text": "groove~ trane_capture 2",
     "patching_rect": [
      470.0,
      235.0,
      165.0,
      22.0
     ],
     "numinlets": 3,
     "numoutlets": 3,
     "outlettype": [
      "signal",
      "signal",
      "signal"
     ]
    }
   },
   {
    "box": {
     "id": "obj-11",
     "maxclass": "newobj",
     "text": "sig~ 1.",
     "patching_rect": [
      260.0,
      205.0,
      50.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      "signal"
     ]
    }
   },
   {
    "box": {
     "id": "obj-12",
     "maxclass": "message",
     "text": "0, 1 5, 0 90 5",
     "patching_rect": [
      30.0,
      250.0,
      100.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-13",
     "maxclass": "newobj",
     "text": "line~",
     "patching_rect": [
      150.0,
      250.0,
      40.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 2,
     "outlettype": [
      "signal",
      "bang"
     ]
    }
   },
   {
    "box": {
     "id": "obj-14",
     "maxclass": "newobj",
     "text": "*~",
     "patching_rect": [
      470.0,
      300.0,
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
     "id": "obj-15",
     "maxclass": "newobj",
     "text": "*~",
     "patching_rect": [
      550.0,
      300.0,
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
     "id": "obj-16",
     "maxclass": "outlet",
     "comment": "left",
     "patching_rect": [
      470.0,
      370.0,
      25.0,
      25.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-17",
     "maxclass": "outlet",
     "comment": "right",
     "patching_rect": [
      550.0,
      370.0,
      25.0,
      25.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-18",
     "maxclass": "newobj",
     "text": "thispoly~",
     "patching_rect": [
      650.0,
      80.0,
      55.0,
      22.0
     ],
     "numinlets": 1,
     "numoutlets": 1,
     "outlettype": [
      "int"
     ]
    }
   },
   {
    "box": {
     "id": "obj-19",
     "maxclass": "message",
     "text": "mute 0",
     "patching_rect": [
      650.0,
      120.0,
      48.0,
      22.0
     ]
    }
   },
   {
    "box": {
     "id": "obj-20",
     "maxclass": "comment",
     "text": "One voice reads the shared rolling buffer. The root patch dispatches up to six voices to keep Intel i5 load bounded.",
     "patching_rect": [
      30.0,
      420.0,
      680.0,
      20.0
     ]
    }
   }
  ],
  "lines": [
   {
    "patchline": {
     "source": [
      "obj-1",
      0
     ],
     "destination": [
      "obj-2",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-2",
      0
     ],
     "destination": [
      "obj-3",
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
      "obj-4",
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
      "obj-4",
      1
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
      "obj-4",
      0
     ],
     "destination": [
      "obj-6",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-5",
      0
     ],
     "destination": [
      "obj-6",
      1
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
      "obj-7",
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
      "obj-8",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-8",
      1
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
      "obj-8",
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
      "obj-9",
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
      "obj-3",
      2
     ],
     "destination": [
      "obj-11",
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
      "obj-10",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-2",
      0
     ],
     "destination": [
      "obj-12",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-12",
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
      "obj-10",
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
      "obj-10",
      1
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
      "obj-14",
      1
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
      "obj-15",
      1
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
      "obj-16",
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
      "obj-17",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-2",
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
      "obj-18",
      0
     ]
    }
   }
  ]
 }
}
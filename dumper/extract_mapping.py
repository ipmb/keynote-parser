#!/usr/bin/xcrun python3
"""
Launch Keynote (or technically Pages, or any other iWork app), set a
breakpoint at the first reasonable method after everything is loaded,
then dump the contents of `TSPRegistry sharedRegistry` to a JSON file.

Nastiest hack. Please don't use this.
Copyright 2020 Peter Sobot (psobot.com).
"""

import os
import sys
import json
import lldb

exe = sys.argv[-1]
debugger = lldb.SBDebugger.Create()
debugger.SetAsync(False)
target = debugger.CreateTargetWithFileAndArch(exe, None)
target.BreakpointCreateByName("_sendFinishLaunchingNotification")
target.BreakpointCreateByName("_handleAEOpenEvent:")
# To get around the fact that we don't have iCloud entitlements when running re-signed code,
# let's break in the CloudKit code and early exit the function before it can raise an exception:
target.BreakpointCreateByName("[CKContainer containerWithIdentifier:]")

process = target.LaunchSimple(None, None, os.getcwd())

if not process:
    raise ValueError("Failed to launch process: " + exe)
try:
    if process.GetState() == lldb.eStateStopped:
        thread = process.GetThreadAtIndex(0)
        if thread.GetStopReason() == lldb.eStopReasonBreakpoint:
            if thread.GetSelectedFrame().name == '+[CKContainer containerWithIdentifier:]':
                # Skip the code in CKContainer, avoiding a crash due to missing entitlements:
                thread.ReturnFromFrame(thread.GetSelectedFrame(), lldb.SBValue().CreateValueFromExpression("0", ""))
                process.Continue()
    if process.GetState() == lldb.eStateStopped:
        if thread:
            frame = thread.GetFrameAtIndex(0)
            if frame:
                registry = frame.EvaluateExpression('[TSPRegistry sharedRegistry]').description
                split = [
                    x.strip().split(" -> ")
                    for x in registry.split("{")[1].split("}")[0].split("\n")
                    if x.strip()
                ]
                print(
                    json.dumps(
                        dict(
                            sorted(
                                [(int(a), b.split(" ")[-1]) for a, b in split if 'null' not in b]
                            )
                        ),
                        indent=2,
                    )
                )
            else:
                raise ValueError("Could not get frame to print out registry!")
    else:
        raise ValueError("LLDB was unable to stop process! " + str(process))
finally:
    process.Kill()

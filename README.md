# What
This is a small script that combined with the help of pre-packaged DLL's scans nearby wifi networks and prints the results. 
# Why
There exists [winwifi](https://github.com/changyuheng/winwifi.py) and similarly [node-wifi](https://github.com/friedrith/node-wifi) but both of those libraries have the same flaw when running on Windows systems.
They utilize the `netsh` Windows command which retrieves only a *cached* version of the wireless networks. `netsh` does not request a re-scan from the underlying hardware.
To do that we must use utilize Windows API's using C++ or C#.

> The networks are updated only when a scan is completed by your WiFi card. The NETSH command does not request a scan; it only displays the cached results of the last scan.
> -- <cite>[superuser ashleedawg][1]</cite>
>
[1]: https://superuser.com/a/1356083/490393

That's where this script comes in.
It forces a re-scan using the DLL's included in this repo and only *then* calls `netsh`. 
# Who
This is for users running python on Windows machines who want to monitor the availability and names of surrounding wifi networks. It will not work on other operating systems.
It will work on both x86 and 64-bit architectures.
# How
You can use the [scan.py](scan.py) from the CLI. By default, it will just print the results of each scan that produces new results to the screen.

Use by executing the command:

```python scan.py```
 
If you want to store the results of each call into a file (this will also write errors to a separate file), you can execute the command:
  
```python scan.py -verbose-logging```

# Notes

The original source code for the C++ code can be found [here](https://superuser.com/a/1436051/490393). It was written by [user541686](https://superuser.com/users/59271/user541686).
The [wlanscan.cpp](wlanscan.cpp) version of the code was modified to enable DLL support.
 
The [wlanscan.cpp](wlanscan.cpp) file is present just for reference. It's not actually used by the script.
The [WlanScan32Arch.dll](WlanScan32Arch.dll) and [WlanScan64Arch.dll](WlanScan64Arch.dll) DLL's were built by using Visual Studio 2019's default DLL build system.

# Thanks
My main thanks has to go to [user541686](https://superuser.com/users/59271/user541686) who provided the CPP code to actually perform a refresh.
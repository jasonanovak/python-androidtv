# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

The existing python-androidtv library does not support modern adb connections that are called "adb wifi" connections and are described here - https://android.googlesource.com/platform/packages/modules/adb/+/15ffcacbfa1fed4bb59af1a96b9edc9604ba38a4/docs/dev/adb_wifi.md.

The library used to connect to an android device using adb wifi has been updated in a separate Claude session and is located in ../adb_shell. This code should be **read only** and incorporated by reference/import to this project.

The goal of this project is to update the existing python-androidtv library to use the new adb wifi support in the adb_shell fork mentioned above and maintain backwards compatibilty.

The output of this project should be a branch of the python-androidtv library that supports backwards compatibility and can be eventually upstreamed.

The Claude session that modified the adb_shell library to have wifi support wrote a document, WIFI_MIGRATION.md that can be used as a general guide to extending existing usage of adb_shell with the new wifi functionality while not breaking backwards compatibility.


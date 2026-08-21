[app]
title = JARVIS
package.name = jarvis_assistant
package.domain = org.stark.jarvis
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,html,css,js,json
version = 2.1.0

# Requirements (Clean recipe names without == pins)
requirements = python3,kivy,flask,requests,urllib3,charset-normalizer,idna,jinja2,werkzeug,pyjnius

orientation = portrait
fullscreen = 0
android.archs = arm64-v8a
android.allow_backup = True
android.permissions = INTERNET,ACCESS_NETWORK_STATE,RECORD_AUDIO,WAKE_LOCK
android.api = 34
android.minapi = 24
android.ndk_api = 24
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1

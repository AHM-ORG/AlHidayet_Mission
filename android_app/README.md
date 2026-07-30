# 📱 Al-Hidayet Mission Native Android APK Setup

This directory contains the complete **Native Android WebView Application** for **Al-Hidayet Mission**, designed with full support for Apple Liquid Glass UI, file uploads, hardware acceleration, and back-button navigation.

---

## 🚀 How to Build the `.apk` File

### Method 1: Android Studio (Recommended & Easiest)
1. Open **Android Studio**.
2. Click **Open** and select the folder: `c:\Users\mdasw\Desktop\Ahm PAH\AlHidayet_Mission\android_app`.
3. Wait for Gradle sync to complete.
4. Go to **Build** > **Build Bundle(s) / APK(s)** > **Build APK(s)**.
5. Once complete, click **locate** to get your compiled `app-debug.apk` file!
6. Transfer `app-debug.apk` to any Android phone and install it!

---

### Method 2: Command Line (Gradle Wrapper)
```bash
cd android_app
gradlew assembleDebug
```
The generated APK will be saved to:
`android_app/app/build/outputs/apk/debug/app-debug.apk`

---

## ⚙️ Connecting to your Server Domain / IP

In `android_app/app/src/main/java/com/alhidayetmission/app/MainActivity.java`:
- Change `SERVER_URL` to your production domain or local Wi-Fi IP address:
```java
// For Android Emulator testing:
private static final String SERVER_URL = "http://10.0.2.2:5001";

// For local phone testing on same Wi-Fi:
private static final String SERVER_URL = "http://192.168.x.x:5001";

// For live production server:
private static final String SERVER_URL = "https://your-domain.com";
```

---

## 📱 Progressive Web App (PWA) Mode
Your Flask app now also includes:
- `static/manifest.json`
- `static/sw.js`

Users visiting the website on Android Chrome can also click **"Install App"** to install it directly without an APK!

import { Config } from "@remotion/cli/config";

// The card is composited over the footage, so it must carry alpha all the way:
// JPEG frames or a non-alpha pixel format turn the transparent area black.
Config.setVideoImageFormat("png");
Config.setPixelFormat("yuva444p10le");
Config.setCodec("prores");
Config.setProResProfile("4444");

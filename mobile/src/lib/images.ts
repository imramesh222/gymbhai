/**
 * Pictures in and out: a payment screenshot or a photo picked and shrunk
 * before upload, the gym's payment QR saved to the gallery (to pay from the
 * wallet app), and a receipt PDF shared through the phone's share sheet.
 */
import { File, Paths } from "expo-file-system";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";
import { Asset, requestPermissionsAsync } from "expo-media-library";
import * as Sharing from "expo-sharing";

import type { ReceiptLink } from "@shared/types";

import { apiUrl } from "./config";
import type { UploadFile } from "./memberApi";

/** Big enough to read a transaction ID; small enough for slow mobile data. */
const MAX_WIDTH = 1280;

async function shrink(uri: string, name: string): Promise<UploadFile> {
  const image = await ImageManipulator.manipulate(uri)
    .resize({ width: MAX_WIDTH })
    .renderAsync();
  const saved = await image.saveAsync({ compress: 0.7, format: SaveFormat.JPEG });
  return { uri: saved.uri, name, type: "image/jpeg" };
}

/** From the gallery (a screenshot) or the camera. Null if they backed out. */
export async function pickImage(
  from: "gallery" | "camera",
  name: string,
): Promise<UploadFile | null> {
  const options: ImagePicker.ImagePickerOptions = {
    mediaTypes: ["images"],
    quality: 1,
  };
  if (from === "camera") {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) throw new Error("camera_denied");
  }
  const result =
    from === "camera"
      ? await ImagePicker.launchCameraAsync({
          ...options,
          cameraType: ImagePicker.CameraType.front,
        })
      : await ImagePicker.launchImageLibraryAsync(options);
  if (result.canceled || !result.assets[0]) return null;
  return shrink(result.assets[0].uri, name);
}

/** The gym's payment QR into the photos, to open from the wallet app. */
export async function saveToPhotos(imagePath: string): Promise<void> {
  const { granted } = await requestPermissionsAsync(true);
  if (!granted) throw new Error("photos_denied");
  const file = new File(Paths.cache, `payment-qr-${Date.now()}.png`);
  await File.downloadFileAsync(apiUrl(imagePath), file);
  await Asset.create(file.uri);
}

/** Download the receipt and open the share sheet (WhatsApp, Viber, Files...). */
export async function shareReceipt(link: ReceiptLink): Promise<void> {
  const file = new File(Paths.cache, link.filename);
  if (file.exists) file.delete();
  await File.downloadFileAsync(apiUrl(link.url), file);
  await Sharing.shareAsync(file.uri, {
    mimeType: "application/pdf",
    UTI: "com.adobe.pdf",
    dialogTitle: link.text,
  });
}

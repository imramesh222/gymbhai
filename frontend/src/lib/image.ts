/**
 * Shrink a photo before upload. Phone cameras produce 3-5 MB images; a member
 * photo needs about 100 KB, and gym Wi-Fi is often slow.
 */
export async function shrinkImage(
  file: File,
  maxSide = 1024,
  quality = 0.85,
): Promise<Blob> {
  if (!file.type.startsWith("image/")) return file;
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) return file;
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) =>
    canvas.toBlob((blob) => resolve(blob ?? file), "image/jpeg", quality),
  );
}

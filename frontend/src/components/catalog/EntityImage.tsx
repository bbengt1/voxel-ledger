/**
 * Authenticated entity image (generalized from ProductImage, #259 → epic #267).
 *
 * The image endpoint is behind bearer auth, so a plain `<img src>` (fetched
 * by the browser without our Authorization header) won't work. This fetches
 * the image as a blob via the authenticated client and renders it from an
 * object URL, showing a placeholder when the entity has no image (404) or
 * the fetch fails. `basePath` is the entity URL (e.g. `/api/v1/parts/{id}`);
 * the component requests `${basePath}/image`.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { cn } from "@/lib/cn";

interface Props {
  basePath: string;
  size?: "full" | "thumb";
  className?: string;
  /** Bust the blob cache after an upload/delete by changing this. */
  refreshKey?: number;
  alt?: string;
  testIdPrefix?: string;
}

export function EntityImage({
  basePath,
  size = "thumb",
  className,
  refreshKey = 0,
  alt = "Image",
  testIdPrefix = "entity-image",
}: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setFailed(false);
    setUrl(null);
    apiClient
      .get(`${basePath}/image`, { params: { size }, responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data as Blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [basePath, size, refreshKey]);

  if (failed || !url) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded bg-muted text-[10px] text-muted-foreground",
          className,
        )}
        data-testid={`${testIdPrefix}-placeholder`}
        aria-label="No image"
      >
        {failed ? "No image" : "…"}
      </div>
    );
  }

  return (
    <img
      src={url}
      alt={alt}
      className={cn("rounded object-cover", className)}
      data-testid={testIdPrefix}
    />
  );
}

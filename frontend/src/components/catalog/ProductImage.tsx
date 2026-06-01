/**
 * Authenticated product image (#259).
 *
 * The image endpoint is behind bearer auth, so a plain `<img src>` (which
 * the browser fetches without our Authorization header) won't work. This
 * component fetches the image as a blob via the authenticated client,
 * renders it from an object URL, and shows a placeholder when the product
 * has no image (404) or the fetch fails.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { cn } from "@/lib/cn";

interface Props {
  productId: string;
  size?: "full" | "thumb";
  className?: string;
  /** Bust the blob cache after an upload/delete by changing this. */
  refreshKey?: number;
  alt?: string;
}

export function ProductImage({
  productId,
  size = "thumb",
  className,
  refreshKey = 0,
  alt = "Product image",
}: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setFailed(false);
    setUrl(null);
    apiClient
      .get(`/api/v1/products/${productId}/image`, {
        params: { size },
        responseType: "blob",
      })
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
  }, [productId, size, refreshKey]);

  if (failed || !url) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded bg-muted text-[10px] text-muted-foreground",
          className,
        )}
        data-testid="product-image-placeholder"
        aria-label="No product image"
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
      data-testid="product-image"
    />
  );
}

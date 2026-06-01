/**
 * Authenticated product image (#259) — thin wrapper over the generic
 * {@link EntityImage} (epic #267 generalized this so parts reuse it).
 */
import { EntityImage } from "@/components/catalog/EntityImage";

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
  return (
    <EntityImage
      basePath={`/api/v1/products/${productId}`}
      size={size}
      className={className}
      refreshKey={refreshKey}
      alt={alt}
      testIdPrefix="product-image"
    />
  );
}

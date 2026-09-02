from app.domain import CanonicalCategory

TAXONOMY: tuple[CanonicalCategory, ...] = (
    CanonicalCategory.PRODUCT_UX,
    CanonicalCategory.CORE,
    CanonicalCategory.DATA,
    CanonicalCategory.PLATFORM,
    CanonicalCategory.RELIABILITY,
    CanonicalCategory.QUALITY,
    CanonicalCategory.OPERATIONS,
    CanonicalCategory.DEVELOPER,
)

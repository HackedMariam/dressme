"""
Request models with strict validation - every string is trimmed and length-bounded, numbers are
range-checked, ids and enums are pattern-checked. Unknown fields are ignored on the item models
(the frontend sends whole result objects back) and rejected on the new endpoints (auth, analytics).
"""

from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator

CATEGORIES = ("shirts", "pants", "dresses", "shoes", "outerwear", "accessories")
MAX_IMAGE_B64 = 14 * 1024 * 1024  # 10 MB of image data, base64-encoded, plus the data-URL prefix

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Attribute = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]
Brand = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_\-]{1,64}$")]
ImageData = Annotated[str, StringConstraints(min_length=16, max_length=MAX_IMAGE_B64)]
Price = Annotated[float, Field(ge=0, le=100_000)]


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _normalize_category(value):
    if isinstance(value, str):
        value = value.strip().lower()
    return value


Category = Annotated[Literal["shirts", "pants", "dresses", "shoes", "outerwear", "accessories"],
                     BeforeValidator(_normalize_category)]


# ----------------------------------------------------------------------------
# Items & analyses
# ----------------------------------------------------------------------------

class ClothingItemRequest(_Lenient):
    id: Optional[Annotated[str, StringConstraints(max_length=64)]] = None
    name: Name
    category: Category
    color: Optional[Attribute] = None       # real products may miss color / material - the engine handles None
    style: Optional[Attribute] = "casual"
    material: Optional[Attribute] = None
    use_case: Optional[Attribute] = "casual"
    season: Optional[Attribute] = None
    price: Optional[Price] = None
    brand: Optional[Brand] = None
    description: Optional[Description] = None
    product_id: Optional[Identifier] = None
    image_url: Optional[Annotated[str, StringConstraints(max_length=500)]] = None
    image_embedding: Optional[List[float]] = Field(default=None, max_length=512)



class AnalysisRequest(_Lenient):
    new_item: ClothingItemRequest
    wardrobe_items: Optional[List[ClothingItemRequest]] = Field(default=None, max_length=500)  # None -> saved wardrobe
    image_base64: Optional[ImageData] = None   # photo of the new item (data URL or base64)
    product_id: Optional[Identifier] = None    # or a catalog product (its photo is compared)
    use_llm: bool = True
    language: Annotated[str, StringConstraints(pattern=r"^[A-Za-z\- ]{2,20}$")] = "English"


class WardrobeItemRequest(_Lenient):
    name: Optional[Name] = None
    category: Optional[Category] = None
    color: Optional[Attribute] = None
    style: Optional[Attribute] = None
    material: Optional[Attribute] = None
    use_case: Optional[Attribute] = None
    season: Optional[Attribute] = None
    brand: Optional[Brand] = None
    price: Optional[Price] = None
    size: Optional[Annotated[str, StringConstraints(max_length=10)]] = None
    product_id: Optional[Identifier] = None    # add a catalog product
    image_base64: Optional[ImageData] = None   # or a photo (attributes auto-detected when missing)



class WardrobeUpdateRequest(_Lenient):
    name: Optional[Name] = None
    category: Optional[Category] = None
    color: Optional[Attribute] = None
    style: Optional[Attribute] = None
    material: Optional[Attribute] = None
    use_case: Optional[Attribute] = None
    brand: Optional[Brand] = None
    price: Optional[Price] = None
    size: Optional[Annotated[str, StringConstraints(max_length=10)]] = None



class ChatTurn(_Strict):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class AgentRunRequest(_Lenient):
    mission: Literal["purchase", "audit", "outfits", "shopping", "declutter", "ask"] = "purchase"
    message: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""
    history: List[ChatTurn] = Field(default_factory=list, max_length=12)  # earlier turns of the conversation
    item: Optional[Dict[str, Any]] = None
    image_base64: Optional[ImageData] = None
    budget: Optional[Annotated[float, Field(ge=0, le=1_000_000)]] = None
    mode: Literal["auto", "local", "claude", "llm"] = "auto"

    @field_validator("item")
    @classmethod
    def _small_item(cls, value):
        if value is not None and (len(value) > 30 or len(str(value)) > 5000):
            raise ValueError("item is too large")
        return value


class AgentRequest(_Lenient):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    wardrobe_items: List[ClothingItemRequest] = Field(default_factory=list, max_length=500)
    max_iterations: int = Field(default=8, ge=1, le=15)


class FeedbackRequest(_Lenient):
    item_id: Identifier
    feedback_type: Annotated[str, StringConstraints(pattern=r"^[a-z_]{2,30}$")]
    rating: int = Field(ge=0, le=5)
    comment: Optional[Annotated[str, StringConstraints(max_length=1000)]] = None
    helped_decision: Optional[bool] = None


class CameraCaptureRequest(_Lenient):
    image_base64: ImageData


# ----------------------------------------------------------------------------
# Accounts
# ----------------------------------------------------------------------------

Gender = Literal["Women", "Men", "Unspecified"]
ClothingSize = Literal["XS", "S", "M", "L", "XL", "XXL"]
ShoeSize = Annotated[str, StringConstraints(pattern=r"^(3[0-9]|4[0-9]|50)(\.5)?$")]  # EU 30-50
StylePreference = Literal["casual", "sporty", "formal", "classic", "business", "minimalist", "streetwear",
                          "vintage", "bohemian", "trendy"]
ColorName = Annotated[str, StringConstraints(pattern=r"^[a-z]{3,12}$")]


class ProfileFields(_Strict):
    """Profile attributes - they adapt the starter wardrobe, the catalog filter and the sizes of the pieces"""
    display_name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]] = None
    gender: Optional[Gender] = None
    clothing_size: Optional[ClothingSize] = None
    shoe_size: Optional[ShoeSize] = None
    style_preferences: Optional[List[StylePreference]] = Field(default=None, max_length=5)
    favorite_colors: Optional[List[ColorName]] = Field(default=None, max_length=8)


class RegisterRequest(ProfileFields):
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=5, max_length=255)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    import_guest_data: bool = False  # move the guest wardrobe & history into the new account
    starter_wardrobe: bool = False   # add 40+ catalog pieces adapted to the profile


class ProfileUpdate(ProfileFields):
    pass


class LoginRequest(_Strict):
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=255)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


# ----------------------------------------------------------------------------
# Client analytics
# ----------------------------------------------------------------------------

class ClientEventIn(_Strict):
    name: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
    page: Optional[Annotated[str, StringConstraints(pattern=r"^[a-z0-9_\-]{1,64}$")]] = None
    properties: Optional[Dict[str, Any]] = None

    @field_validator("properties")
    @classmethod
    def _flat_and_small(cls, value):
        if value is None:
            return value
        if len(value) > 20:
            raise ValueError("at most 20 properties")
        for key, item in value.items():
            if len(key) > 40 or not isinstance(item, (str, int, float, bool, type(None))):
                raise ValueError("properties must be flat scalars")
            if isinstance(item, str) and len(item) > 200:
                raise ValueError("property values are limited to 200 characters")
        return value


class ClientEventBatch(_Strict):
    session_id: Optional[Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9\-]{8,64}$")]] = None
    events: List[ClientEventIn] = Field(min_length=1, max_length=50)

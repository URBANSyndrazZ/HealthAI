from typing import Any

from app.tools.registry import tool_registry

NUTRITION_DB = {
    "米饭": {"calories": 130, "protein": 2.7, "carbs": 28, "fat": 0.3, "fiber": 0.4, "unit": "100g"},
    "面条": {"calories": 138, "protein": 4.5, "carbs": 25, "fat": 2.1, "fiber": 1.2, "unit": "100g"},
    "鸡胸肉": {"calories": 165, "protein": 31, "carbs": 0, "fat": 3.6, "fiber": 0, "unit": "100g"},
    "牛肉": {"calories": 250, "protein": 26, "carbs": 0, "fat": 15, "fiber": 0, "unit": "100g"},
    "猪肉": {"calories": 242, "protein": 27, "carbs": 0, "fat": 14, "fiber": 0, "unit": "100g"},
    "鸡蛋": {"calories": 155, "protein": 13, "carbs": 1.1, "fat": 11, "fiber": 0, "unit": "100g"},
    "牛奶": {"calories": 42, "protein": 3.4, "carbs": 5, "fat": 1, "fiber": 0, "unit": "100ml"},
    "苹果": {"calories": 52, "protein": 0.3, "carbs": 14, "fat": 0.2, "fiber": 2.4, "unit": "100g"},
    "香蕉": {"calories": 89, "protein": 1.1, "carbs": 23, "fat": 0.3, "fiber": 2.6, "unit": "100g"},
    "西兰花": {"calories": 34, "protein": 2.8, "carbs": 7, "fat": 0.4, "fiber": 2.6, "unit": "100g"},
    "胡萝卜": {"calories": 41, "protein": 0.9, "carbs": 10, "fat": 0.2, "fiber": 2.8, "unit": "100g"},
    "西红柿": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2, "fiber": 1.2, "unit": "100g"},
    "土豆": {"calories": 77, "protein": 2, "carbs": 17, "fat": 0.1, "fiber": 2.2, "unit": "100g"},
    "豆腐": {"calories": 76, "protein": 8, "carbs": 1.9, "fat": 4.8, "fiber": 0.3, "unit": "100g"},
    "豆浆": {"calories": 45, "protein": 3.6, "carbs": 1.8, "fat": 2.4, "fiber": 0, "unit": "100ml"},
    "酸奶": {"calories": 59, "protein": 10, "carbs": 3.6, "fat": 0.4, "fiber": 0, "unit": "100g"},
    "燕麦": {"calories": 389, "protein": 16.9, "carbs": 66, "fat": 6.9, "fiber": 10.6, "unit": "100g"},
    "全麦面包": {"calories": 247, "protein": 13, "carbs": 41, "fat": 3.4, "fiber": 7, "unit": "100g"},
    "白面包": {"calories": 265, "protein": 9, "carbs": 49, "fat": 3.2, "fiber": 2.7, "unit": "100g"},
    "橄榄油": {"calories": 884, "protein": 0, "carbs": 0, "fat": 100, "fiber": 0, "unit": "100g"},
    "花生酱": {"calories": 588, "protein": 25, "carbs": 20, "fat": 50, "fiber": 6, "unit": "100g"},
    "坚果混合": {"calories": 607, "protein": 20, "carbs": 21, "fat": 54, "fiber": 7, "unit": "100g"},
    "巧克力": {"calories": 546, "protein": 4.9, "carbs": 61, "fat": 31, "fiber": 7, "unit": "100g"},
    "蜂蜜": {"calories": 304, "protein": 0.3, "carbs": 82, "fat": 0, "fiber": 0.2, "unit": "100g"},
    "白糖": {"calories": 387, "protein": 0, "carbs": 100, "fat": 0, "fiber": 0, "unit": "100g"},
    "盐": {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0, "sodium": 38758, "unit": "100g"},
}

def _calculate_multiplier(amount: float, unit: str) -> float:
    unit = unit.lower()
    if unit in ("g", "gram", "grams"):
        return amount / 100
    if unit in ("kg", "kilogram", "kilograms"):
        return amount * 10
    if unit in ("oz", "ounce", "ounces"):
        return amount * 0.283495
    if unit in ("lb", "lbs", "pound", "pounds"):
        return amount * 4.53592
    if unit in ("ml", "milliliter", "milliliters"):
        return amount / 100
    if unit in ("l", "liter", "liters"):
        return amount * 10
    if unit in ("cup", "cups"):
        return amount * 2.4
    if unit in ("tbsp", "tablespoon", "tablespoons"):
        return amount * 0.15
    if unit in ("tsp", "teaspoon", "teaspoons"):
        return amount * 0.05
    if unit in ("serving", "servings", "piece", "pieces", "slice", "slices"):
        return amount * 1.5
    if unit in ("bowl", "bowls"):
        return amount * 3
    if unit in ("plate", "plates"):
        return amount * 4
    return amount / 100

def query_nutrition_tool(food_name: str, amount: float, unit: str) -> dict[str, Any]:
    """Query nutrition facts and calculate totals for one food item."""
    nutrition_per_100g = None
    for db_food, db_nutrition in NUTRITION_DB.items():
        if db_food in food_name or food_name in db_food:
            nutrition_per_100g = dict(db_nutrition)
            break

    if nutrition_per_100g is None:
        nutrition_per_100g = {
            "calories": 100,
            "protein": 5,
            "carbs": 15,
            "fat": 3,
            "fiber": 1,
        }

    multiplier = _calculate_multiplier(float(amount or 0), unit or "serving")
    total_nutrition = {
        key: value * multiplier
        for key, value in nutrition_per_100g.items()
        if key not in {"unit", "sodium"}
    }
    return {
        "per_100g": nutrition_per_100g,
        "total": total_nutrition,
        "multiplier": multiplier,
        "data_source": "local_nutrition_tool",
    }

tool_registry.register(
    "query_nutrition",
    "Query local nutrition facts and calculate totals for one food item.",
    query_nutrition_tool,
    {
        "type": "object",
        "properties": {
            "food_name": {"type": "string"},
            "amount": {"type": "number"},
            "unit": {"type": "string"}
        },
        "required": ["food_name"],
    }
)
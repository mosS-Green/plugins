from app.modules.list_reminder import load_data
from app.config import Config

async def get_my_list(user_id: int | str | None = None) -> str:
    if not user_id:
        user_id = Config.OWNER_ID
    data = await load_data()
    user_list = data.get(str(user_id), [])
    if not user_list:
        return "Your list is empty."
    
    lines = []
    for i, item in enumerate(user_list, 1):
        text = item["text"]
        # Simplified for AI context, no need for HTML/links if just reading content, 
        # but link might be useful. 
        if "link" in item:
            lines.append(f"{i}. {text} (Link: {item['link']})")
        else:
            lines.append(f"{i}. {text}")
            
    return "\n".join(lines)

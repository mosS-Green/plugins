from ..lastfm import get_now_playing_track, LASTFM_DB
from ub_core import bot

async def get_my_lastfm_status(user_id: int):
    """
    Checks the Last.fm status of the user (or the bot owner/Leaf if not specified, 
    though logic here typically requires a user ID to look up in DB).
    
    Args:
        user_id (int): The Telegram User ID of the person asking.
    """
    try:
        # 1. Fetch Last.fm username from DB
        fren_info = await LASTFM_DB.find_one({"_id": user_id})
        
        if not fren_info or "lastfm_username" not in fren_info:
            return "User is not logged in to Last.fm (not a 'fren'). Use /afren to login."
            
        username = fren_info["lastfm_username"]
        first_name = fren_info.get("name", "User")
        
        # 2. Get Track Data
        data = await get_now_playing_track(username)
        
        if isinstance(data, str):
            return f"Error fetching Last.fm status: {data}"
            
        # 3. Format Response for AI
        action = "is vibing to" if data["is_now_playing"] else "was listening to"
        track = data["track_name"]
        artist = data["artist_name"]
        plays = data["play_count"]
        time_ago = f" ({data['last_played_time']})" if data["last_played_time"] else ""
        
        return f"{first_name} {action} {track} by {artist}. [Plays: {plays}]{time_ago}"

    except Exception as e:
        return f"An error occurred while checking Last.fm status: {str(e)}"

import discord
from discord import app_commands
from core.classes import Cog_Extension
from tweety import Twitter
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
import sqlite3

from src.log import setup_logger
from src.notification.account_tracker import AccountTracker
from src.permission_check import is_administrator

log = setup_logger(__name__)

load_dotenv()

class Notification(Cog_Extension):
    def __init__(self, bot):
        super().__init__(bot)
        self.account_tracker = AccountTracker(bot)

    add_group = app_commands.Group(name='add', description="Add something")
    remove_group = app_commands.Group(name='remove', description='Remove something')


    @is_administrator()
    @add_group.command(name='notifier')
    async def notifier(self, itn : discord.Interaction, username: str, channel: discord.TextChannel, mention: discord.Role = None):
        """Add a twitter user to specific channel on your server.

        Parameters
        -----------
        username: str
            The username of the twitter user you want to turn on notifications for.
        channel: discord.TextChannel
            The channel to which the bot delivers notifications.
        mention: discord.Role
            The role to mention when notifying.
        """
        
        await itn.response.defer(ephemeral=True)
        
        conn = sqlite3.connect(f"{os.getenv('DATA_PATH')}tracked_accounts.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM user WHERE username = ?', (username,))
        match_user = cursor.fetchone()
        
        server_id = str(itn.guild_id)
        roleID = str(mention.id) if mention != None else ''
        mention_str = mention.mention if mention else ''
        if match_user == None:
            app = Twitter("session")
            app.load_auth_token(os.getenv('TWITTER_TOKEN'))
            try:
                new_user = app.get_user_info(username)
            except:
                await itn.followup.send(f'user {username} not found', ephemeral=True)
                return
            
            cursor.execute('INSERT INTO user VALUES (?, ?, ?)', (str(new_user.id), username, datetime.utcnow().replace(tzinfo=timezone.utc).strftime('%Y-%m-%d %H:%M:%S%z')))
            cursor.execute('INSERT OR IGNORE INTO channel VALUES (?)', (str(channel.id),))
            cursor.execute('INSERT INTO notification (user_id, channel_id, role_id, mention, server_id) VALUES (?, ?, ?, ?, ?)', (str(new_user.id), str(channel.id), roleID, mention_str, server_id))
            
            app.follow_user(new_user)
            
            if app.enable_user_notification(new_user): log.info(f'successfully opened notification for {username}')
            else: log.warning(f'unable to turn on notifications for {username}')
        else:
            cursor.execute('INSERT OR IGNORE INTO channel VALUES (?)', (str(channel.id),))
            cursor.execute('REPLACE INTO notification (user_id, channel_id, role_id, mention) VALUES (?, ?, ?)', (match_user['id'], str(channel.id), roleID, mention_str))
        
        conn.commit()
        conn.close()
            
        if match_user == None: await self.account_tracker.addTask(username)
            
        await itn.followup.send(f'successfully add notifier of {username}!', ephemeral=True)


    @is_administrator()
    @remove_group.command(name='notifier')
    async def remove_notifier(self, itn: discord.Interaction, username: str):
        """Remove a notifier on your server.

        Parameters
        -----------
        username: str
            The username of the twitter user you want to turn off notifications for.
        channel: discord.TextChannel
            The channel which set to delivers notifications.
        """  
        await itn.response.defer(ephemeral=True)
        
        conn = sqlite3.connect(f"{os.getenv('DATA_PATH')}tracked_accounts.db")
        cursor = conn.cursor()
        
        server_id = str(itn.guild_id)

        cursor.execute(f"SELECT * FROM user WHERE username='{username}'")
        match_user = cursor.fetchone()
        
        if match_user is None:
            await itn.followup.send(f'can\'t find notifier{username}', ephemeral=True)
            return
        
        await self.account_tracker.removeTask(username)
        
        cursor.execute(f"DELETE FROM user WHERE username='{username}'")
        cursor.execute(f"DELETE FROM notification WHERE user_id='{match_user[0]}' AND server_id='{server_id}'")
        
        conn.commit()
        conn.close()

        app = Twitter("session")
        app.load_auth_token(os.getenv('TWITTER_TOKEN'))
        user_info = app.get_user_info(username)
        app.unfollow_user(user_info)
        app.disable_user_notification(user_info)
        
        await self.account_tracker.clear_cancelled_tasks()  

        await itn.followup.send(f'successfully remove notifier of{username}', ephemeral=True)


async def setup(bot):
	await bot.add_cog(Notification(bot))
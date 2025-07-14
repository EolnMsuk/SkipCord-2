import asyncio
import logging
from typing import Optional, Union

import discord
from discord.ext import commands
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# Local application imports
import config  # For SKIP_COMMAND_KEY
from tools import BotConfig

# Constants
DRIVER_INIT_RETRIES = 2
DRIVER_INIT_DELAY = 5

class OmegleHandler:
    """Handles all Selenium browser automation for Omegle."""

    def __init__(self, bot_config: BotConfig):
        self.config = bot_config
        self.driver: Optional[webdriver.Edge] = None
        self._driver_initialized = False

    async def initialize(self) -> bool:
        """
        Initializes the Selenium WebDriver in a non-blocking way.
        Returns True if successful, False otherwise.
        """
        for attempt in range(DRIVER_INIT_RETRIES):
            try:
                if self.driver is not None:
                    await self.close()

                # Run blocking webdriver_manager install in a separate thread
                service_path = await asyncio.to_thread(EdgeChromiumDriverManager().install)
                service = EdgeService(service_path)
                
                options = webdriver.EdgeOptions()
                options.add_argument("--log-level=3")
                options.add_argument('--ignore-certificate-errors')
                options.add_argument('--allow-running-insecure-content')
                options.add_argument(f"user-data-dir={self.config.EDGE_USER_DATA_DIR}")

                # Run blocking driver instantiation in a separate thread
                self.driver = await asyncio.to_thread(webdriver.Edge, service=service, options=options)
                
                await asyncio.to_thread(self.driver.maximize_window)
                await asyncio.to_thread(self.driver.get, self.config.OMEGLE_VIDEO_URL)
                
                self._driver_initialized = True
                logging.info("Selenium driver initialized successfully.")
                return True
            except WebDriverException as e:
                logging.error(f"Selenium initialization attempt {attempt + 1} failed: {e}")
                if attempt < DRIVER_INIT_RETRIES - 1:
                    await asyncio.sleep(DRIVER_INIT_DELAY)
            except Exception as e:
                logging.error(f"Unexpected error during Selenium initialization: {e}")
                break
        logging.critical("Failed to initialize Selenium driver after retries. The bot will continue without browser automation.")
        self._driver_initialized = False
        return False

    async def is_healthy(self) -> bool:
        """Checks if Selenium driver is responsive."""
        if not self._driver_initialized or self.driver is None:
            return False
        try:
            # Run blocking property access in a separate thread
            await asyncio.to_thread(lambda: self.driver.current_url)
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Safely closes Selenium driver."""
        if self.driver is not None:
            try:
                await asyncio.to_thread(self.driver.quit)
                logging.info("Selenium driver closed.")
            except Exception as e:
                logging.error(f"Error closing Selenium driver: {e}")
            finally:
                self.driver = None
                self._driver_initialized = False

    async def custom_skip(self, ctx: Optional[commands.Context] = None) -> bool:
        """
        Sends skip key events to the page.
        Returns True if successful, False otherwise.
        """
        if not await self.is_healthy():
            if ctx:
                await ctx.send("Browser connection is not available. Please restart the bot manually.")
            return False
            
        keys = getattr(config, "SKIP_COMMAND_KEY", ["Escape", "Escape"])
        if not isinstance(keys, list):
            keys = [keys]
        try:
            for i, key in enumerate(keys):
                script = f"""
                var evt = new KeyboardEvent('keydown', {{
                    bubbles: true,
                    cancelable: true,
                    key: '{key}',
                    code: '{key}'
                }});
                document.dispatchEvent(evt);
                """
                await asyncio.to_thread(self.driver.execute_script, script)
                logging.info(f"Selenium: Sent {key} key event to page.")
                if i < len(keys) - 1:
                    await asyncio.sleep(1)
            return True
        except Exception as e:
            logging.error(f"Selenium custom skip failed: {e}")
            if ctx:
                await ctx.send("Failed to execute skip command in browser.")
            return False

    async def refresh(self, ctx: Optional[Union[commands.Context, discord.Message, discord.Interaction]] = None, is_pause: bool = False) -> bool:
        """Handles both refresh and pause functionality."""
        if not await self.is_healthy():
            msg = "Browser connection is not available. Please restart the bot manually."
            if ctx:
                if isinstance(ctx, discord.Interaction):
                    if ctx.response.is_done(): await ctx.followup.send(msg)
                    else: await ctx.response.send_message(msg)
                elif hasattr(ctx, 'send'):
                    await ctx.send(msg)
            return False
        
        try:
            if is_pause:
                await asyncio.to_thread(self.driver.refresh)
                log_msg = "Selenium: Refresh performed for pause command."
                response_msg = "Stream paused temporarily!"
            else:
                await asyncio.to_thread(self.driver.get, self.config.OMEGLE_VIDEO_URL)
                log_msg = "Selenium: Navigated to OMEGLE_VIDEO_URL for refresh command."
                response_msg = "Page refreshed!"
            
            logging.info(log_msg)
            
            if ctx:
                if isinstance(ctx, discord.Interaction):
                    if ctx.response.is_done(): await ctx.followup.send(response_msg)
                    else: await ctx.response.send_message(response_msg)
                elif hasattr(ctx, 'send'):
                    await ctx.send(response_msg)
            
            return True
        except Exception as e:
            log_error = f"Selenium {'pause' if is_pause else 'refresh'} failed: {e}"
            logging.error(log_error)
            
            if ctx:
                error_msg = f"Failed to process {'pause' if is_pause else 'refresh'} command in browser."
                if isinstance(ctx, discord.Interaction):
                    if ctx.response.is_done(): await ctx.followup.send(error_msg)
                    else: await ctx.response.send_message(error_msg)
                elif hasattr(ctx, 'send'):
                    await ctx.send(error_msg)
            return False

    async def start_stream(self, ctx: Optional[Union[commands.Context, discord.Interaction]] = None, is_paid: bool = False) -> bool:
        """
        Starts the stream by navigating to OMEGLE_VIDEO_URL and triggering a skip.
        Returns True if successful, False otherwise.
        """
        if not await self.is_healthy():
            msg = "Browser connection is not available. Please restart the bot manually."
            if ctx:
                if isinstance(ctx, discord.Interaction):
                    if ctx.response.is_done(): await ctx.followup.send(msg)
                    else: await ctx.response.send_message(msg)
                else:
                    await ctx.send(msg)
            return False
        
        try:
            await asyncio.to_thread(self.driver.get, self.config.OMEGLE_VIDEO_URL)
            log_msg = "Selenium: Navigated to OMEGLE_VIDEO_URL for paid command." if is_paid else "Selenium: Navigated to OMEGLE_VIDEO_URL for start."
            logging.info(log_msg)
            
            if ctx:
                response_msg = "Redirected to Omegle video URL." if is_paid else "Stream started!"
                if isinstance(ctx, discord.Interaction):
                    if ctx.response.is_done(): await ctx.followup.send(response_msg)
                    else: await ctx.response.send_message(response_msg)
                elif hasattr(ctx, 'send'):
                    await ctx.send(response_msg)
            
            await asyncio.sleep(3)
            return await self.custom_skip(ctx)
        except Exception as e:
            log_error = f"Selenium {'paid' if is_paid else 'start'} failed: {e}"
            logging.error(log_error)
            
            if ctx:
                error_msg = f"Failed to process {'paid' if is_paid else 'start'} command in browser."
                if isinstance(ctx, discord.Interaction):
                    if ctx.response.is_done(): await ctx.followup.send(error_msg)
                    else: await ctx.response.send_message(error_msg)
                elif hasattr(ctx, 'send'):
                    await ctx.send(error_msg)
            return False

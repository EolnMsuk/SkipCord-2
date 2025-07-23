# omegle.py
# This file contains the OmegleHandler class, which is responsible for all browser
# automation tasks using Selenium. It manages the WebDriver lifecycle and provides
# methods to interact with the Omegle web page.

import asyncio
import os
from functools import wraps
from typing import Optional, Union

import discord
from discord.ext import commands
from selenium import webdriver
from selenium.common.exceptions import WebDriverException, StaleElementReferenceException
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from loguru import logger

# Local application imports
import config  # Used for SKIP_COMMAND_KEY if defined
from tools import BotConfig

# Constants
DRIVER_INIT_RETRIES = 2     # Number of times to retry initializing the WebDriver if it fails.
DRIVER_INIT_DELAY = 5       # Seconds to wait between retry attempts.

def require_healthy_driver(func):
    """
    A decorator that checks if the Selenium WebDriver is initialized and responsive
    before allowing a method to execute. If the driver is not healthy, it will
    attempt to relaunch it. If the relaunch fails, it notifies the user.
    """
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        # A helper to find a context object (ctx) from the function's arguments to send a reply.
        def find_context() -> Optional[Union[commands.Context, discord.Message, discord.Interaction]]:
            ctx = None
            if args:
                ctx_candidate = args[0]
                if isinstance(ctx_candidate, (commands.Context, discord.Message, discord.Interaction)):
                    return ctx_candidate
            if 'ctx' in kwargs:
                ctx_candidate = kwargs['ctx']
                if isinstance(ctx_candidate, (commands.Context, discord.Message, discord.Interaction)):
                    return ctx_candidate
            return None

        # A helper to send a message to a context object, handling different context types.
        async def send_to_context(ctx, msg, ephemeral=False):
            if not ctx: return
            try:
                if isinstance(ctx, discord.Interaction):
                    if ctx.response.is_done(): await ctx.followup.send(msg, ephemeral=ephemeral)
                    else: await ctx.response.send_message(msg, ephemeral=ephemeral)
                elif hasattr(ctx, 'send'):
                    await ctx.send(msg)
            except Exception as e:
                logger.error(f"Failed to send message to context: {e}")

        # Check the health of the driver.
        if not await self.is_healthy():
            logger.warning("Driver is unhealthy. Attempting to relaunch the browser...")
            ctx = find_context()
            
            await send_to_context(ctx, "Browser connection lost. Attempting to relaunch...")

            # Attempt to re-initialize the driver. The initialize() method already handles closing the old one.
            if not await self.initialize():
                logger.critical("Failed to relaunch the browser after retries. Manual restart required.")
                await send_to_context(ctx, "Failed to relaunch the browser. Please restart the bot manually.", ephemeral=True)
                return False # Indicate that the relaunch failed.
            
            logger.info("Browser relaunched successfully.")
            await send_to_context(ctx, "Browser has been successfully relaunched.")

        # If the driver was healthy initially OR was successfully relaunched, execute the original function.
        return await func(self, *args, **kwargs)
    return wrapper


class OmegleHandler:
    """
    Manages all Selenium WebDriver interactions for controlling the Omegle stream.
    This includes initializing the browser, navigating, and sending commands.
    """

    def __init__(self, bot_config: BotConfig):
        self.config = bot_config
        self.driver: Optional[webdriver.Edge] = None
        self._driver_initialized = False # A flag to track if the driver has been successfully initialized.

    async def initialize(self) -> bool:
        """
        Initializes the Selenium Edge WebDriver. It first tries to use a specific driver path
        from the config, and if that fails or isn't provided, it falls back to automatically
        downloading and managing the driver with `webdriver-manager`.
        
        Returns:
            True if the driver was initialized successfully, False otherwise.
        """
        for attempt in range(DRIVER_INIT_RETRIES):
            try:
                if self.driver is not None:
                    await self.close() # Ensure any existing driver is closed before creating a new one.

                driver_path = None
                # 1. Try using the driver path specified in the config file.
                if self.config.EDGE_DRIVER_PATH and isinstance(self.config.EDGE_DRIVER_PATH, str):
                    if os.path.exists(self.config.EDGE_DRIVER_PATH):
                        driver_path = self.config.EDGE_DRIVER_PATH
                        logger.info(f"Using configured WebDriver path: {driver_path}")
                    else:
                        logger.warning(
                            f"Configured WebDriver path not found: {self.config.EDGE_DRIVER_PATH}. "
                            "Falling back to automatic download."
                        )

                # 2. If no valid path was found, fall back to automatic management.
                if not driver_path:
                    logger.info("Initializing Selenium WebDriver with webdriver-manager...")
                    # This blocking call is run in a separate thread to not halt the event loop.
                    driver_path = await asyncio.to_thread(EdgeChromiumDriverManager().install)

                if not driver_path:
                    logger.critical("Could not determine WebDriver path. Retrying...")
                    await asyncio.sleep(DRIVER_INIT_DELAY)
                    continue

                # Set up the service and options for the Edge browser.
                service = EdgeService(executable_path=driver_path)
                options = webdriver.EdgeOptions()
                options.add_argument("--log-level=3") # Suppress console noise.
                options.add_argument('--ignore-certificate-errors')
                options.add_argument('--allow-running-insecure-content')
                # Use a specific user profile to remember logins and settings.
                options.add_argument(f"user-data-dir={self.config.EDGE_USER_DATA_DIR}")

                # Run the blocking webdriver instantiation in a separate thread.
                self.driver = await asyncio.to_thread(webdriver.Edge, service=service, options=options)

                # Navigate to the target URL.
                await asyncio.to_thread(self.driver.maximize_window)
                await asyncio.to_thread(self.driver.get, self.config.OMEGLE_VIDEO_URL)

                self._driver_initialized = True
                logger.info(f"Selenium driver initialized successfully from path: {driver_path}")
                return True
            except WebDriverException as e:
                logger.error(f"Selenium initialization attempt {attempt + 1} failed: {e}")
                if "This version of Microsoft Edge Driver only supports" in str(e):
                    logger.critical("CRITICAL: WebDriver version mismatch. Please update Edge browser or check for driver issues.")
                if attempt < DRIVER_INIT_RETRIES - 1:
                    await asyncio.sleep(DRIVER_INIT_DELAY)
            except Exception as e:
                logger.error(f"Unexpected error during Selenium initialization: {e}", exc_info=True)
                break
        
        logger.critical("Failed to initialize Selenium driver after retries. The bot will continue without browser automation.")
        self._driver_initialized = False
        return False

    async def is_healthy(self) -> bool:
        """
        Checks if the Selenium driver is initialized and still responsive.
        It does this by attempting to access a simple property (`current_url`).
        """
        if not self._driver_initialized or self.driver is None:
            return False
        try:
            # Run the blocking property access in a separate thread.
            await asyncio.to_thread(lambda: self.driver.current_url)
            return True
        except Exception:
            # Any exception here (e.g., browser crashed) means the driver is not healthy.
            return False

    async def close(self) -> None:
        """Safely closes the Selenium driver and quits the browser."""
        if self.driver is not None:
            try:
                # `driver.quit()` is a blocking call.
                await asyncio.to_thread(self.driver.quit)
                logger.info("Selenium driver closed.")
            except Exception as e:
                logger.error(f"Error closing Selenium driver: {e}")
            finally:
                self.driver = None
                self._driver_initialized = False

    @require_healthy_driver
    async def custom_skip(self, ctx: Optional[commands.Context] = None) -> bool:
        """
        Executes a "skip" action on the web page by injecting JavaScript to simulate
        keyboard events (e.g., pressing the Escape key twice).
        
        Returns:
            True if successful, False otherwise.
        """
        # Get the keys to press from the config, defaulting to Escape, Escape.
        keys = getattr(config, "SKIP_COMMAND_KEY", ["Escape", "Escape"])
        if not isinstance(keys, list):
            keys = [keys]

        # Retry loop to handle potential `StaleElementReferenceException`, which can happen
        # if the page structure changes while the command is running.
        for attempt in range(3):
            try:
                # Loop through the configured keys and dispatch a keydown event for each.
                for i, key in enumerate(keys):
                    script = f"""
                    var evt = new KeyboardEvent('keydown', {{
                        bubbles: true, cancelable: true, key: '{key}', code: '{key}'
                    }});
                    document.dispatchEvent(evt);
                    """
                    # Execute the JavaScript in a separate thread.
                    await asyncio.to_thread(self.driver.execute_script, script)
                    logger.info(f"Selenium: Sent {key} key event to page.")
                    if i < len(keys) - 1:
                        await asyncio.sleep(1) # Wait between key presses if multiple are configured.
                return True  # Success, exit the function.
            except StaleElementReferenceException:
                logger.warning(f"StaleElementReferenceException on attempt {attempt + 1}. Retrying...")
                await asyncio.sleep(0.5)
                continue  # Retry the operation.
            except Exception as e:
                logger.error(f"Selenium custom skip failed: {e}")
                if ctx: await ctx.send("Failed to execute skip command in browser.")
                return False

        logger.error("Failed to execute custom skip after multiple retries due to stale elements.")
        if ctx: await ctx.send("Failed to execute skip command after multiple retries.")
        return False

    @require_healthy_driver
    async def refresh(self, ctx: Optional[Union[commands.Context, discord.Message, discord.Interaction]] = None) -> bool:
        """
        Refreshes the stream page by navigating the browser back to the configured video URL.
        This is often used to fix a disconnected or frozen stream.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            # `driver.get()` is a blocking call.
            await asyncio.to_thread(self.driver.get, self.config.OMEGLE_VIDEO_URL)
            logger.info("Selenium: Navigated to OMEGLE_VIDEO_URL for refresh command.")
            return True
        except Exception as e:
            logger.error(f"Selenium refresh failed: {e}")
            if ctx:
                error_msg = "Failed to process refresh command in browser."
                if isinstance(ctx, discord.Interaction):
                    if ctx.response.is_done(): await ctx.followup.send(error_msg)
                    else: await ctx.response.send_message(error_msg)
                elif hasattr(ctx, 'send'):
                    await ctx.send(error_msg)
            return False

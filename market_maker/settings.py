# API URL.
#BASE_URL = "https://testnet.bitmex.com/api/v1/"
BASE_URL = "https://www.bitmex.com/api/v1/" # Once you're ready, uncomment this.

# The BitMEX API requires permanent API keys. Go to https://testnet.bitmex.com/app/apiKeys to fill these out.
API_KEY = "ZJ7ZG0bDrem884wQkNnvv2PB"
API_SECRET = "wbFfEOkZqut7OG8rueCPTmEsCsYHyqxakxlg1dNoZbz7EJ6w"

SYMBOL = 'ETHUSD'

# Wait times between orders / errors
API_REST_INTERVAL = 1
API_ERROR_INTERVAL = 10
TIMEOUT = 7

# Available levels: logging.(DEBUG|INFO|WARN|ERROR)
LOG_LEVEL = logging.INFO

# If any of these files (and this file) changes, reload the bot.
WATCHED_FILES = [join('market_maker', 'market_maker.py'), join('market_maker', 'bitmex.py'), 'settings.py']

# always amend orders
RELIST_INTERVAL = 0.00

# hyperparameters
GAMMA = 15
K = 30
D = 0.99
THETA = 25
ETA = 0.004
ETA2 = 0.0006
MAX_POS = 150


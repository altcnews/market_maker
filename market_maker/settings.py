import logging
from os.path import join
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
LOG_LEVEL = logging.DEBUG

# If any of these files (and this file) changes, reload the bot.
WATCHED_FILES = [join('market_maker', 'market_maker.py'), join('market_maker', 'bitmex.py'), join('market_maker', 'settings.py')]

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

DRY_RUN = False
POST_ONLY = True

# Not necessary:
#=================
ORDER_PAIRS = 6

# ORDER_START_SIZE will be the number of contracts submitted on level 1
# Number of contracts from level 1 to ORDER_PAIRS - 1 will follow the function
# [ORDER_START_SIZE + ORDER_STEP_SIZE (Level -1)]
ORDER_START_SIZE = 100
ORDER_STEP_SIZE = 100

# Distance between successive orders, as a percentage (example: 0.005 for 0.5%)
INTERVAL = 0.005

# Minimum spread to maintain, in percent, between asks & bids
MIN_SPREAD = 0.01

# If True, market-maker will place orders just inside the existing spread and work the interval % outwards,
# rather than starting in the middle and killing potentially profitable spreads.
MAINTAIN_SPREADS = True

# This number defines far much the price of an existing order can be from a desired order before it is amended.
# This is useful for avoiding unnecessary calls and maintaining your ratelimits.
#
# Further information:
# Each order is designed to be (INTERVAL*n)% away from the spread.
# If the spread changes and the order has moved outside its bound defined as
# abs((desired_order['price'] / order['price']) - 1) > settings.RELIST_INTERVAL)
# it will be resubmitted.
#
# 0.01 == 1%
RELIST_INTERVAL = 0.01

CHECK_POSITION_LIMITS = False
MIN_POSITION = -10000
MAX_POSITION = 10000

#========================


# Might be necessary
#=======================
LOOP_INTERVAL = 5

# Wait times between orders / errors
API_REST_INTERVAL = 1
API_ERROR_INTERVAL = 10
TIMEOUT = 7

# If we're doing a dry run, use these numbers for BTC balances
DRY_BTC = 50
ORDERID_PREFIX = "mm_bitmex_"
CONTRACTS = ['ETHUSD']
# ===========================

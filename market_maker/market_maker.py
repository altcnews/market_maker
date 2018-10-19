from __future__ import absolute_import
from time import sleep
import sys
import datetime
from os.path import getmtime
import random
import requests
import atexit
import signal

from market_maker import bitmex
from market_maker.settings import settings
from market_maker.utils import log, constants, errors, math

import threading
import numpy as np
from decimal import *
import pandas as pd 
import ccxt

# Used for reloading the bot - saves modified times of key files
import os
watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]


#
# Helpers
#
logger = log.setup_custom_logger('root')

GAMMA = settings.GAMMA
K = settings.K
D = settings.D
THETA = settings.THETA
ETA = settings.ETA
ETA2 = settings.ETA2
MAX_POS = settings.MAX_POS

class ExchangeInterface:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        if len(sys.argv) > 1:
            self.symbol = sys.argv[1]
        else:
            self.symbol = settings.SYMBOL
        self.bitmex = bitmex.BitMEX(base_url=settings.BASE_URL, symbol=self.symbol,
                                    apiKey=settings.API_KEY, apiSecret=settings.API_SECRET,
                                    orderIDPrefix=settings.ORDERID_PREFIX, postOnly=settings.POST_ONLY,
                                    timeout=settings.TIMEOUT)

    def cancel_order(self, order):
        tickLog = self.get_instrument()['tickLog']
        logger.info("Canceling: %s %d @ %.*f" % (order['side'], order['orderQty'], tickLog, order['price']))
        while True:
            try:
                self.bitmex.cancel(order['orderID'])
                sleep(settings.API_REST_INTERVAL)
            except ValueError as e:
                logger.info(e)
                sleep(settings.API_ERROR_INTERVAL)
            else:
                break

    def cancel_all_orders(self):
        if self.dry_run:
            return

        logger.info("Resetting current position. Canceling all existing orders.")
        tickLog = self.get_instrument()['tickLog']

        # In certain cases, a WS update might not make it through before we call this.
        # For that reason, we grab via HTTP to ensure we grab them all.
        orders = self.bitmex.http_open_orders()

        for order in orders:
            logger.info("Canceling: %s %d @ %.*f" % (order['side'], order['orderQty'], tickLog, order['price']))

        if len(orders):
            self.bitmex.cancel([order['orderID'] for order in orders])

        sleep(settings.API_REST_INTERVAL)

    def get_portfolio(self):
        contracts = settings.CONTRACTS
        portfolio = {}
        for symbol in contracts:
            position = self.bitmex.position(symbol=symbol)
            instrument = self.bitmex.instrument(symbol=symbol)

            if instrument['isQuanto']:
                future_type = "Quanto"
            elif instrument['isInverse']:
                future_type = "Inverse"
            elif not instrument['isQuanto'] and not instrument['isInverse']:
                future_type = "Linear"
            else:
                raise NotImplementedError("Unknown future type; not quanto or inverse: %s" % instrument['symbol'])

            if instrument['underlyingToSettleMultiplier'] is None:
                multiplier = float(instrument['multiplier']) / float(instrument['quoteToSettleMultiplier'])
            else:
                multiplier = float(instrument['multiplier']) / float(instrument['underlyingToSettleMultiplier'])

            portfolio[symbol] = {
                "currentQty": float(position['currentQty']),
                "futureType": future_type,
                "multiplier": multiplier,
                "markPrice": float(instrument['markPrice']),
                "spot": float(instrument['indicativeSettlePrice'])
            }

        return portfolio

    def calc_delta(self):
        """Calculate currency delta for portfolio"""
        portfolio = self.get_portfolio()
        spot_delta = 0
        mark_delta = 0
        for symbol in portfolio:
            item = portfolio[symbol]
            if item['futureType'] == "Quanto":
                spot_delta += item['currentQty'] * item['multiplier'] * item['spot']
                mark_delta += item['currentQty'] * item['multiplier'] * item['markPrice']
            elif item['futureType'] == "Inverse":
                spot_delta += (item['multiplier'] / item['spot']) * item['currentQty']
                mark_delta += (item['multiplier'] / item['markPrice']) * item['currentQty']
            elif item['futureType'] == "Linear":
                spot_delta += item['multiplier'] * item['currentQty']
                mark_delta += item['multiplier'] * item['currentQty']
        basis_delta = mark_delta - spot_delta
        delta = {
            "spot": spot_delta,
            "mark_price": mark_delta,
            "basis": basis_delta
        }
        return delta

    def get_delta(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.get_position(symbol)['currentQty']

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.instrument(symbol)

    def get_margin(self):
        if self.dry_run:
            return {'marginBalance': float(settings.DRY_BTC), 'availableFunds': float(settings.DRY_BTC)}
        return self.bitmex.funds()

    def get_orders(self):
        if self.dry_run:
            return []
        return self.bitmex.open_orders()

    def get_highest_buy(self):
        buys = [o for o in self.get_orders() if o['side'] == 'Buy']
        if not len(buys):
            return {'price': -2**32}
        highest_buy = max(buys or [], key=lambda o: o['price'])
        return highest_buy if highest_buy else {'price': -2**32}

    def get_lowest_sell(self):
        sells = [o for o in self.get_orders() if o['side'] == 'Sell']
        if not len(sells):
            return {'price': 2**32}
        lowest_sell = min(sells or [], key=lambda o: o['price'])
        return lowest_sell if lowest_sell else {'price': 2**32}  # ought to be enough for anyone

    def get_position(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.position(symbol)

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.ticker_data(symbol)

    def is_open(self):
        """Check that websockets are still open."""
        return not self.bitmex.ws.exited

    def check_market_open(self):
        instrument = self.get_instrument()
        if instrument["state"] != "Open" and instrument["state"] != "Closed":
            raise errors.MarketClosedError("The instrument %s is not open. State: %s" %
                                           (self.symbol, instrument["state"]))

    def check_if_orderbook_empty(self):
        """This function checks whether the order book is empty"""
        instrument = self.get_instrument()
        if instrument['midPrice'] is None:
            raise errors.MarketEmptyError("Orderbook is empty, cannot quote")

    def amend_bulk_orders(self, orders):
        if self.dry_run:
            return orders
        return self.bitmex.amend_bulk_orders(orders)

    def create_bulk_orders(self, orders):
        if self.dry_run:
            return orders
        return self.bitmex.create_bulk_orders(orders)

    def cancel_bulk_orders(self, orders):
        if self.dry_run:
            return orders
        return self.bitmex.cancel([order['orderID'] for order in orders])

class OrderManager:
    def __init__(self):
        self.exchange = ExchangeInterface(settings.DRY_RUN)
        # Once exchange is created, register exit handler that will always cancel orders
        # on any error.
        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

        logger.info("Using symbol %s." % self.exchange.symbol)

        if settings.DRY_RUN:
            logger.info("Initializing dry run. Orders printed below represent what would be posted to BitMEX.")
        else:
            logger.info("Order Manager initializing, connecting to BitMEX. Live run: executing real trades.")

        self.start_time = datetime.datetime.now()
        self.instrument = self.exchange.get_instrument()
        self.starting_qty = self.exchange.get_delta()
        self.running_qty = self.starting_qty
        self.reset()

        self.cur_volatility = None
        self.act_volatility = None
        self.streak = 0
        self.prev_len = 0
        self.cur_len = 0
        self.idle = 0
        self.first = True
        self.sleep_ctr = 0
        self.general_ctr = 0

        exchange = ccxt.bitmex()
        date_N_days_ago = (datetime.datetime.now() - datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        since = time.mktime(datetime.datetime.strptime(date_N_days_ago, "%Y-%m-%d %H:%M:%S").timetuple())*1000
        df = exchange.fetch_ohlcv('ETH/USD', timeframe = '1m', since=since, limit=500)
        df = pd.DataFrame(df)
        df.columns = ["Timestamp", "Open", "High", "Low", "tick", "Volume"]

        self.df = pd.DataFrame({'tick': df.tick.values.tolist()})

    def reset(self):
        self.exchange.cancel_all_orders()
        self.sanity_check()
        self.print_status()

        # Create orders and converge.
        self.place_orders()

    def print_status(self):
        """Print the current MM status."""

        margin = self.exchange.get_margin()
        position = self.exchange.get_position()
        self.running_qty = self.exchange.get_delta()
        tickLog = self.exchange.get_instrument()['tickLog']
        self.start_XBt = margin["marginBalance"]

        logger.info("Current XBT Balance: %.6f" % XBt_to_XBT(self.start_XBt))
        logger.info("Current Contract Position: %d" % self.running_qty)
        if settings.CHECK_POSITION_LIMITS:
            logger.info("Position limits: %d/%d" % (settings.MIN_POSITION, settings.MAX_POSITION))
        if position['currentQty'] != 0:
            logger.info("Avg Cost Price: %.*f" % (tickLog, float(position['avgCostPrice'])))
            logger.info("Avg Entry Price: %.*f" % (tickLog, float(position['avgEntryPrice'])))
        logger.info("Contracts Traded This Run: %d" % (self.running_qty - self.starting_qty))
        logger.info("Total Contract Delta: %.4f XBT" % self.exchange.calc_delta()['spot'])

    def get_ticker(self):
        ticker = self.exchange.get_ticker()
        tickLog = self.exchange.get_instrument()['tickLog']

        # Midpoint, used for simpler order placement.
        self.start_position_mid = ticker["mid"]
        logger.info("%s Ticker: New Mid %.*f" % (self.instrument['symbol'], self.start_position_mid))
        return ticker

    def calc_res_price(self, mid, qty, vola):
        #print (qty)
        VAR = vola
        r = mid - (qty*GAMMA*VAR*D)/MAX_POS
        spread = max(0.1, GAMMA*VAR*D + np.log(1+GAMMA/K))
        return r, spread

    def get_qty(self, qty):
        buy_qty = THETA*np.exp(-ETA2*qty) if qty < 0 else THETA*np.exp(-ETA*qty)
        sell_qty = THETA*np.exp(ETA2*qty) if qty > 0 else THETA*np.exp(ETA*qty)
        return int(round(buy_qty)), int(round(sell_qty))

    def one_loop(self):
        ticker = self.get_ticker()
        pos = self.get_delta()

        if self.ctr == 4:
            self.ctr = 0
            self.df = self.df.append(pd.DataFrame({'tick': [ticker['mid']]}), ignore_index = True)
            if len(self.df) > 60:
                # self.write = True
                self.df = self.df.iloc[-80:]
                self.df['ret'] = (self.df['tick'] - self.df['tick'].shift())**2
                self.df['vola'] = self.df['ret'].rolling(60).apply(np.mean)
                self.cur_volatility = self.df.iloc[-1].vola
                print ("Volatility: ", self.cur_volatility)
                logging.info('Full minute -- Volatility: {}'.format(self.cur_volatility))
            if self.first:
                print (self.df.tail(5))
                print (self.df.iloc[-1], self.df.iloc[-1].tick, self.df.iloc[-2], self.df.iloc[-2].tick)

        ord_list = self.exchange.get_orders()

        if self.first == True and pos != 0:
            self.first = False
        if self.first == True and len(ord_list) != 0:
            self.first = False

        if (self.df.iloc[-1].tick == self.df.iloc[-2].tick) and (self.df.iloc[-3].tick == self.df.iloc[-2].tick):
            print ('Repetition! RESTART TRIGGERING')
            logging.info('Repetition! RESTART TRIGGERING')
            self.restart()

        if (self.df.iloc[-1].tick == self.df.iloc[-2].tick) and (self.df.iloc[-3].tick == self.df.iloc[-2].tick):
            print ('Repetition! RESTART TRIGGERING')
            logging.info('Repetition! RESTART TRIGGERING')
            self.restart()

        # no need for automatic restart for now
        # if self.general_ctr == 2880:
        #     print ('RAN FOR 12 HRS! RESTART TRIGGERING')
        #     logging.info('RAN FOR 12 HRS! RESTART TRIGGERING')
        #     self.general_ctr = 0
        #     self.restart()

        self.cur_len = len(ord_list)
        if (self.cur_len == self.prev_len) and (self.cur_len > 0): # could incur errors
            self.idle += 1
        elif (self.cur_len < self.prev_len):
            self.streak += 1
            self.idle = 0 #wont use idle for now
        else:
            self.idle = 0

        logging.info('Subminute -- Mid price {}; Position Size: {}; OrderList: {}; OrderLength: {}'.format(ticker['mid'], pos, ord_list, len(ord_list)))

        if self.act_volatility != None: #abrupt change in volatility
            cond1 = self.cur_volatility > self.act_volatility*1.25
            cond2 = self.cur_volatility < self.act_volatility*.75
        else:
            cond1 = cond2 = False

        cond3 = (self.cur_volatility != None) and (self.first) # no order placed before + enough data to calc volatility
        cond4 = (ord_list != None) and (ord_list != []) and (len(ord_list) < 2) and (self.cur_len < self.prev_len) # 1 order just filled --> left 1 order on the other side
        #cond5 = (self.idle == 60) # if orders don't get filled for too long
        cond5 = False
        cond6 = (ord_list == [] and self.first == False) # no orders after the first trade
        cond7 = (ord_list != None) and (ord_list != []) and (len(ord_list) < 2) and (ord_list[0]['side'] == 'Buy') and (pos != 0) and (pos > 0) # 1 order left + on the same side of the pos
        cond8 = (ord_list != None) and (ord_list != []) and (len(ord_list) < 2) and (ord_list[0]['side'] == 'Sell') and (pos != 0) and (pos < 0) # 1 order left + on the same side of the pos
        cond9 = (len(ord_list) >= 10)

        if self.streak == 3:
            logging.info('Sleep to prevent successive market orders.')
            cond4 = False
            self.sleep_ctr += 1

        logging.info('assess conditions: {}, {}, {}, {}, {}, {}, {}, {}, {}'.format(cond1, cond2, cond3, cond4, cond5, cond6, cond7, cond8, cond9))
        if cond1 or cond2 or cond3 or cond4 or cond5 or cond6 or cond7 or cond8 or cond9:
            if cond3:
                logging.info('First Trade!')
                self.first = False
            if cond4 or cond1 or cond2 or cond7 or cond8 or cond9:
                logging.info('Revise')
                self.client.Order.Order_cancelAll().result()
            if cond5:
                logging.info('Idle')
                self.idle = 0
            r, spread = self.calc_res_price(ticker["mid"], pos, self.cur_volatility)
            print ('Real mid: ', r)
            print ('Spread: ', spread)
            buy_qty, sell_qty = self.get_qty(pos)
            self.place_orders(spread, r, buy_qty, sell_qty, pos)
            self.act_volatility = self.cur_volatility
            self.cur_len += bool(buy_qty) + bool(sell_qty)
            logging.info('Orders post: {}, {}, {}, {}'.format(r, spread, buy_qty, sell_qty))
        else:
            pass

        self.prev_len = self.cur_len

    def round_to(self, n, precision):
        correction = 0.5 if n >= 0 else -0.5
        return int( n/precision+correction ) * precision

    def round_to_05(self, n):
        return self.round_to(n, 0.05)

    def place_orders(self, spread, mid, buy_qty, sell_qty, pos):
        """Create order items for use in convergence."""

        buy_orders = []
        sell_orders = []
        # Create orders from the outside in. This is intentional - let's say the inner order gets taken;
        # then we match orders from the outside in, ensuring the fewest number of orders are amended and only
        # a new order is created in the inside. If we did it inside-out, all orders would be amended
        # down and a new order would be created at the outside.

        getcontext().prec = 4
        if pos > 0:
            buy = {'orderQty': buy_qty, 'price': self.round_to_05(float(Decimal(mid) - Decimal(spread)/Decimal(2))), 'side': 'Buy', 'execInst': 'ParticipateDoNotInitiate'}
            sell = {'orderQty': sell_qty, 'price': self.round_to_05(float(Decimal(mid) + Decimal(spread)/Decimal(2))), 'side': 'Sell'}
        elif pos < 0:
            buy = {'orderQty': buy_qty, 'price': self.round_to_05(float(Decimal(mid) - Decimal(spread)/Decimal(2))), 'side': 'Buy'}
            sell = {'orderQty': sell_qty, 'price': self.round_to_05(float(Decimal(mid) + Decimal(spread)/Decimal(2))), 'side': 'Sell', 'execInst': 'ParticipateDoNotInitiate'}
        else:
            buy = {'orderQty': buy_qty, 'price': self.round_to_05(float(Decimal(mid) - Decimal(spread)/Decimal(2))), 'side': 'Buy', 'execInst': 'ParticipateDoNotInitiate'}
            sell = {'orderQty': sell_qty, 'price': self.round_to_05(float(Decimal(mid) + Decimal(spread)/Decimal(2))), 'side': 'Sell', 'execInst': 'ParticipateDoNotInitiate'}
        if buy_qty == 0:
            sell_orders.append(sell)
        elif sell_qty == 0:
            buy_orders.append(buy)
        else:
            sell_orders.append(sell)
            buy_orders.append(buy)
        print ('Buy: {}; Sell: {}'.format(buy['price'], sell['price']))
        logging.info('Buy: {}; Sell: {}'.format(buy['price'], sell['price']))
        return self.converge_orders(buy_orders, sell_orders)

    def converge_orders(self, buy_orders, sell_orders):
        """Converge the orders we currently have in the book with what we want to be in the book.
           This involves amending any open orders and creating new ones if any have filled completely.
           We start from the closest orders outward."""

        tickLog = self.exchange.get_instrument()['tickLog']
        to_amend = []
        to_create = []
        to_cancel = []
        buys_matched = 0
        sells_matched = 0
        existing_orders = self.exchange.get_orders()

        # Check all existing orders and match them up with what we want to place.
        # If there's an open one, we might be able to amend it to fit what we want.
        for order in existing_orders:
            try:
                if order['side'] == 'Buy':
                    desired_order = buy_orders[buys_matched]
                    buys_matched += 1
                else:
                    desired_order = sell_orders[sells_matched]
                    sells_matched += 1

                # Found an existing order. Do we need to amend it?
                if desired_order['orderQty'] != order['leavesQty'] or (
                        # If price has changed, and the change is more than our RELIST_INTERVAL, amend.
                        desired_order['price'] != order['price'] and
                        abs((desired_order['price'] / order['price']) - 1) > settings.RELIST_INTERVAL):
                    to_amend.append({'orderID': order['orderID'], 'orderQty': order['cumQty'] + desired_order['orderQty'],
                                     'price': desired_order['price'], 'side': order['side']})
            except IndexError:
                # Will throw if there isn't a desired order to match. In that case, cancel it.
                to_cancel.append(order)

        while buys_matched < len(buy_orders):
            to_create.append(buy_orders[buys_matched])
            buys_matched += 1

        while sells_matched < len(sell_orders):
            to_create.append(sell_orders[sells_matched])
            sells_matched += 1

        if len(to_amend) > 0:
            for amended_order in reversed(to_amend):
                reference_order = [o for o in existing_orders if o['orderID'] == amended_order['orderID']][0]
                logger.info("Amending %4s: %d @ %.*f to %d @ %.*f (%+.*f)" % (
                    amended_order['side'],
                    reference_order['leavesQty'], tickLog, reference_order['price'],
                    (amended_order['orderQty'] - reference_order['cumQty']), tickLog, amended_order['price'],
                    tickLog, (amended_order['price'] - reference_order['price'])
                ))
            # This can fail if an order has closed in the time we were processing.
            # The API will send us `invalid ordStatus`, which means that the order's status (Filled/Canceled)
            # made it not amendable.
            # If that happens, we need to catch it and re-tick.
            try:
                self.exchange.amend_bulk_orders(to_amend)
            except requests.exceptions.HTTPError as e:
                errorObj = e.response.json()
                if errorObj['error']['message'] == 'Invalid ordStatus':
                    logger.warn("Amending failed. Waiting for order data to converge and retrying.")
                    sleep(0.5)
                    return self.place_orders()
                else:
                    logger.error("Unknown error on amend: %s. Exiting" % errorObj)
                    sys.exit(1)

        if len(to_create) > 0:
            logger.info("Creating %d orders:" % (len(to_create)))
            for order in reversed(to_create):
                logger.info("%4s %d @ %.*f" % (order['side'], order['orderQty'], tickLog, order['price']))
            self.exchange.create_bulk_orders(to_create)

        # Could happen if we exceed a delta limit
        if len(to_cancel) > 0:
            logger.info("Canceling %d orders:" % (len(to_cancel)))
            for order in reversed(to_cancel):
                logger.info("%4s %d @ %.*f" % (order['side'], order['leavesQty'], tickLog, order['price']))
            self.exchange.cancel_bulk_orders(to_cancel)

    def sanity_check(self):
        """Perform checks before placing orders."""

        # Check if OB is empty - if so, can't quote.
        self.exchange.check_if_orderbook_empty()

        # Ensure market is still open.
        self.exchange.check_market_open()

    def check_file_change(self):
        """Restart if any files we're watching have changed."""
        for f, mtime in watched_files_mtimes:
            if getmtime(f) > mtime:
                self.restart()

    def check_connection(self):
        """Ensure the WS connections are still open."""
        return self.exchange.is_open()

    def exit(self):
        logger.info("Shutting down. All open orders will be cancelled.")
        try:
            self.exchange.cancel_all_orders()
            self.exchange.bitmex.exit()
        except errors.AuthenticationError as e:
            logger.info("Was not authenticated; could not cancel orders.")
        except Exception as e:
            logger.info("Unable to cancel orders: %s" % e)

        sys.exit()

    def run_loop(self):
        threading.Timer(15.0, self.run_loop).start()
        sys.stdout.write("-----\n")
        sys.stdout.flush()

        self.ctr += 1

        self.check_file_change()
        #sleep(settings.LOOP_INTERVAL)

            # This will restart on very short downtime, but if it's longer,
            # the MM will crash entirely as it is unable to connect to the WS on boot.
        if not self.check_connection():
            logger.error("Realtime data connection unexpectedly closed, restarting.")
            self.restart()

        self.sanity_check()  # Ensures health of mm - several cut-out points here
        self.print_status()  # Print skew, delta, etc

        self.one_loop()  # Creates desired orders and converges to existing orders

    def restart(self):
        logger.info("Restarting the market maker...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

# todo: helper function: convert bitmex symbol to ccxt symbol
def run():
    logger.info('BitMEX Market Maker Version: %s\n' % constants.VERSION)

    om = OrderManager()
    # Try/except just keeps ctrl-c from printing an ugly stacktrace
    try:
        om.run_loop()
    except (KeyboardInterrupt, SystemExit):
        sys.exit()

if __name__ == "__main__":
    current_hour = datetime.datetime.now().hour
    os.environ['TZ'] = 'Asia/Saigon'
    time.tzset() # only available in Unix
    run()
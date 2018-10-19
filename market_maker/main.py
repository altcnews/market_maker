from bitmex_websocket import BitMEXWebsocket
import logging
from time import sleep
import threading
import numpy as np
from decimal import *
import bitmex
import simplejson as json
import pandas as pd 
import ccxt
import datetime
import time
import os
import sys

VAR = 0.02**2
GAMMA = 15
K = 30
D = 0.99
THETA = 25
ETA = 0.004
ETA2 = 0.0006
MAX_POS = 150

logging.basicConfig(filename="marketmakertest1011.log", level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")

# Basic use of websocket.
class Market_maker():
    def __init__(self, symbol):
        self.ctr = 0
        self.symbol = symbol
        #self.logger = self.setup_logger()

        # hoang: wbFfEOkZqut7OG8rueCPTmEsCsYHyqxakxlg1dNoZbz7EJ6w
        # hoang: ZJ7ZG0bDrem884wQkNnvv2PB

        api_key = "ZJ7ZG0bDrem884wQkNnvv2PB" #"9FR7reF9F71NDZG_BDoMsfm9" # 8vXVw923QlDRoRtXSwvwbXlU
        api_secret = "wbFfEOkZqut7OG8rueCPTmEsCsYHyqxakxlg1dNoZbz7EJ6w" #"TiXEEabXxJ_KX5ev_RoOnB-JVQqDdj4AAMJvRBXpPhtAKGVH" # nFZS4qiArohuyY_4J9oGBk49X2iL5LteAXCrHcHveF6j5Gwi

        # Instantiating the WS will make it connect. Be sure to add your api_key/api_secret.
        self.ws = BitMEXWebsocket(endpoint="https://www.bitmex.com/api/v1", symbol=self.symbol,
                             api_key=api_key, api_secret=api_secret)
        self.ws.get_instrument()

        #self.logger.info("Instrument data: %s" % self.ws.get_instrument())
        self.client = bitmex.bitmex(test=False, api_key=api_key, api_secret=api_secret)
        self.last_r = None
        self.last_spread = None
        #self.clean = False

        self.tick = []
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
        #print (df.tail())
        #print (self.df.tail())

        # always fetch df using ccxt
        # check number of pos: if len(pos) > 0 : self.first = False
        logging.info("App Initiated!")

    def restart(self):
        # api_key = "ZJ7ZG0bDrem884wQkNnvv2PB" #"9FR7reF9F71NDZG_BDoMsfm9" # 8vXVw923QlDRoRtXSwvwbXlU
        # api_secret = "wbFfEOkZqut7OG8rueCPTmEsCsYHyqxakxlg1dNoZbz7EJ6w" #"TiXEEabXxJ_KX5ev_RoOnB-JVQqDdj4AAMJvRBXpPhtAKGVH" # nFZS4qiArohuyY_4J9oGBk49X2iL5LteAXCrHcHveF6j5Gwi

        # # Instantiating the WS will make it connect. Be sure to add your api_key/api_secret.
        # self.ws = BitMEXWebsocket(endpoint="https://www.bitmex.com/api/v1", symbol=self.symbol,
        #                      api_key=api_key, api_secret=api_secret)
        # self.ws.get_instrument()
        # self.client = bitmex.bitmex(test=False, api_key=api_key, api_secret=api_secret)
        print ('Restart finished.')
        logging.info("Restarting the market maker...")
        self.clean()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def round_to(self, n, precision):
        correction = 0.5 if n >= 0 else -0.5
        return int( n/precision+correction ) * precision

    def round_to_05(self, n):
        return self.round_to(n, 0.05)

    def test(self):
        print ('Restarting')
        logging.info('Restarting')
        return self.restart()

    def run(self):
        threading.Timer(15.0, self.run).start()
        sys.stdout.write("---------------------\n")
        logging.info("---------------------\n")
        #sys.stdout.flush()
            # TODO 1: write check_file_change & add settings.

            #self.check_file_change()
            #sleep(settings.LOOP_INTERVAL)

            # This will restart on very short downtime, but if it's longer,
            # the MM will crash entirely as it is unable to connect to the WS on boot.
        if not self.check_connection():
            print ('No connection detected! Restarting...')
            logging.error("Realtime data connection unexpectedly closed, restarting.")
            self.restart()

            # TODO 2: sanity_check, print_status    
        self.ctr += 1
        self.general_ctr += 1
        ticker = self.ws.get_ticker()
        self.test = False

        print ('Mid: ', ticker['mid'])
        #logging.info('New Ticker: ', ticker['mid'])

        start_cond = (self.ctr == 1 and len(self.df) > 60)

        if self.ctr == 4:
            print ('FULL MINUTE')
            logging.info('FULL MINUTE')
            self.ctr = 0
            #print ("Df length: ", len(self.df))
            #print(self.df)
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
        try:
            pos = self.client.Position.Position_get().result()[0][-1]['currentQty']
        except:
            pos = 0

        try:
            ord_list = self.client.Order.Order_getOrders(filter=json.dumps({"open": True})).result()[0]
            #print(ord_list)
            #print (len(ord_list))
        except Exception as e:
            ord_list = []
            logging.info('Error when getting OrderList: {}'.format(e))

        if self.test:
            print ('TEST! RESTART TRIGGERING')
            logging.info('TEST! RESTART TRIGGERING')
            self.restart()

        if self.first == True and pos != 0:
            self.first = False
        if self.first == True and len(ord_list) != 0:
            self.first = False

        if (self.df.iloc[-1].tick == self.df.iloc[-2].tick) and (self.df.iloc[-3].tick == self.df.iloc[-2].tick):
            print ('Repetition! RESTART TRIGGERING')
            logging.info('Repetition! RESTART TRIGGERING')
            self.restart()

        if self.general_ctr == 2880:
            print ('RAN FOR 12 HRS! RESTART TRIGGERING')
            logging.info('RAN FOR 12 HRS! RESTART TRIGGERING')
            self.general_ctr = 0
            self.restart()

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
            self.post_orders(spread, r, buy_qty, sell_qty, pos)
            self.act_volatility = self.cur_volatility
            self.cur_len += bool(buy_qty) + bool(sell_qty)
            logging.info('Orders post: {}, {}, {}, {}'.format(r, spread, buy_qty, sell_qty))
        else:
            pass

        self.prev_len = self.cur_len
        

        """
        if self.write:
            self.df.to_csv()
        """


        # if self.ws.api_key:
        #     self.logger.info("Funds: %s" % self.ws.funds())
        #logger.info("Market Depth: %s" % self.ws.market_depth())
        #logger.info("Recent Trades: %s\n\n" % self.ws.recent_trades())

    def collect(self):
        threading.Timer(10.0, self.collect).start()
        self.ctr += 1
        ticker = self.ws.get_ticker()['mid']
        self.tick.append(ticker)
        print ('ticker collected: ', ticker)
        if self.ctr == 360:
            df = pd.DataFrame({'tick': ticker})
            df.to_csv('collected.csv')
            print ('Done!')

    def clean(self):
        print ("CANCEL ALL ORDERS")
        logging.info('CANCEL ALL ORDERS')
        #self.clean = True
        return self.client.Order.Order_cancelAll().result()

    def calc_res_price(self, mid, qty, vola):
        #print (qty)
        VAR = vola
        r = mid - (qty*GAMMA*VAR*D)/MAX_POS
        spread = max(0.1, GAMMA*VAR*D + np.log(1+GAMMA/K))
        return r, spread

    def post_orders(self, spread, mid, buy_qty, sell_qty, pos):
        getcontext().prec = 4
        if pos > 0:
            buy = {'orderQty': buy_qty, 'price': self.round_to_05(float(Decimal(mid) - Decimal(spread)/Decimal(2))), 'side': 'Buy', 'symbol' : self.symbol, 'execInst': 'ParticipateDoNotInitiate'}
            sell = {'orderQty': sell_qty, 'price': self.round_to_05(float(Decimal(mid) + Decimal(spread)/Decimal(2))), 'side': 'Sell', 'symbol' : self.symbol}
        elif pos < 0:
            buy = {'orderQty': buy_qty, 'price': self.round_to_05(float(Decimal(mid) - Decimal(spread)/Decimal(2))), 'side': 'Buy', 'symbol' : self.symbol}
            sell = {'orderQty': sell_qty, 'price': self.round_to_05(float(Decimal(mid) + Decimal(spread)/Decimal(2))), 'side': 'Sell', 'symbol' : self.symbol, 'execInst': 'ParticipateDoNotInitiate'}
        else:
            buy = {'orderQty': buy_qty, 'price': self.round_to_05(float(Decimal(mid) - Decimal(spread)/Decimal(2))), 'side': 'Buy', 'symbol' : self.symbol, 'execInst': 'ParticipateDoNotInitiate'}
            sell = {'orderQty': sell_qty, 'price': self.round_to_05(float(Decimal(mid) + Decimal(spread)/Decimal(2))), 'side': 'Sell', 'symbol' : self.symbol, 'execInst': 'ParticipateDoNotInitiate'}
        if buy_qty == 0:
            to_create = [sell]
        elif sell_qty == 0:
            to_create = [buy]
        else:
            to_create = [buy, sell]
        print ('Buy: {}; Sell: {}'.format(buy['price'], sell['price']))
        logging.info('Buy: {}; Sell: {}'.format(buy['price'], sell['price']))
        self.client.Order.Order_newBulk(orders=json.dumps(to_create)).result()

    def get_qty(self, qty):
        buy_qty = THETA*np.exp(-ETA2*qty) if qty < 0 else THETA*np.exp(-ETA*qty)
        sell_qty = THETA*np.exp(ETA2*qty) if qty > 0 else THETA*np.exp(ETA*qty)
        return int(round(buy_qty)), int(round(sell_qty))

    def setup_logger(self):
        # Prints logger info to terminal
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)  # Change this to DEBUG if you want a lot more info
        ch = logging.StreamHandler()
        # create formatter
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        # add formatter to ch
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        return logger

    def check_connection(self):
        """Ensure the WS connections are still open."""
        print ('STATUS: ', not self.ws.exited)
       	logging.info('STATUS: ', not self.ws.exited)
        return not self.ws.exited

    def run_loop(self):
        while True:
            sys.stdout.write("-----\n")
            sys.stdout.flush()
            # TODO 1: write check_file_change & add settings.

            #self.check_file_change()
            #sleep(settings.LOOP_INTERVAL)

            # This will restart on very short downtime, but if it's longer,
            # the MM will crash entirely as it is unable to connect to the WS on boot.
            if not self.check_connection():
                print ('No connection detected! Restarting...')
                logging.error("Realtime data connection unexpectedly closed, restarting.")
                self.restart()

            # TODO 2: sanity_check, print_status

            self.run()

            #self.sanity_check()  # Ensures health of mm - several cut-out points here
            #self.print_status()  # Print skew, delta, etc
            #self.place_orders()  # Creates desired orders and converges to existing orders


if __name__ == "__main__":
    current_hour = datetime.datetime.now().hour
    os.environ['TZ'] = 'Asia/Saigon'
    time.tzset() # only available in Unix
    Market_maker('ETHUSD').run()
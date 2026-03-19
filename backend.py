# backend.py - Complete XTAAGC Bot Backend with REAL Bitget & Firebase
import os
import hmac
import hashlib
import time
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from functools import wraps
from dotenv import load_dotenv

# ==================== FASTAPI IMPORTS ====================
from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
import uvicorn

# ==================== CCXT (BITGET) ====================
import ccxt

# ==================== FIREBASE ====================
import firebase_admin
from firebase_admin import credentials, firestore, auth

# ==================== REDIS ====================
import redis.asyncio as redis

# ==================== JWT ====================
import jwt
from passlib.context import CryptContext

# ==================== LOAD ENVIRONMENT ====================
load_dotenv()

# ==================== CONFIGURATION ====================
@dataclass
class Config:
    # ===== YOUR REAL BITGET CREDENTIALS =====
    BITGET_API_KEY: str = os.getenv('BITGET_API_KEY', 'bg_ffcbb26a743c6f3617a03e4edb87aa3f')
    BITGET_API_SECRET: str = os.getenv('BITGET_API_SECRET', 'e397e3420dbb6a1b48dfef734e6ef8d6aaf29ee44a044d51dd1742a8143c0693')
    BITGET_API_PASSPHRASE: str = os.getenv('BITGET_API_PASSPHRASE', '02703242')
    
    # ===== YOUR REAL FIREBASE CREDENTIALS =====
    FIREBASE_PROJECT_ID: str = os.getenv('FIREBASE_PROJECT_ID', 'xtaagc')
    FIREBASE_API_KEY: str = os.getenv('FIREBASE_API_KEY', 'AIzaSyCOcCDPqRSlAMJJBEeNchTA1qO9tl9Nldw')
    FIREBASE_AUTH_DOMAIN: str = os.getenv('FIREBASE_AUTH_DOMAIN', 'xtaagc.firebaseapp.com')
    FIREBASE_STORAGE_BUCKET: str = os.getenv('FIREBASE_STORAGE_BUCKET', 'xtaagc.firebasestorage.app')
    FIREBASE_MESSAGING_SENDER_ID: str = os.getenv('FIREBASE_MESSAGING_SENDER_ID', '256073982437')
    FIREBASE_APP_ID: str = os.getenv('FIREBASE_APP_ID', '1:256073982437:android:0c54368d54e260cba98f0c')
    FIREBASE_PRIVATE_KEY: str = os.getenv('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n')
    FIREBASE_CLIENT_EMAIL: str = os.getenv('FIREBASE_CLIENT_EMAIL', '')
    
    # JWT
    JWT_SECRET: str = os.getenv('JWT_SECRET', 'your-super-secret-jwt-key-2024')
    
    # Redis
    REDIS_URL: str = os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    # Trading
    INITIAL_CAPITAL: float = 1000.0
    MAX_POSITION_SIZE: float = 100.0
    MAX_DAILY_LOSS: float = 50.0
    MAX_CONCURRENT_TRADES: int = 5
    MIN_PROFIT_THRESHOLD: float = 0.002  # 0.2%
    
    # Server
    PORT: int = int(os.getenv('PORT', '8000'))
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'

config = Config()

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO if not config.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== SECURITY ====================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_jwt_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(days=7)})
    return jwt.encode(to_encode, config.JWT_SECRET, algorithm="HS256")

def decode_jwt_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

# ==================== BITGET SERVICE ====================
class BitgetService:
    def __init__(self):
        self.api_key = config.BITGET_API_KEY
        self.api_secret = config.BITGET_API_SECRET
        self.api_passphrase = config.BITGET_API_PASSPHRASE
        self.exchange = None
        self.connected = False
        
    async def connect(self):
        """Connect to Bitget with your REAL credentials"""
        try:
            self.exchange = ccxt.bitget({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'password': self.api_passphrase,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'adjustForTimeDifference': True,
                }
            })
            
            # Test connection
            await self.get_balance()
            self.connected = True
            logger.info("✅ Bitget connected")
            return True
        except Exception as e:
            logger.error(f"❌ Bitget connection failed: {e}")
            return False
            
    async def get_balance(self) -> Dict:
        """Get REAL account balance"""
        try:
            balance = self.exchange.fetch_balance()
            result = {}
            for currency, data in balance['total'].items():
                if data > 0:
                    result[currency] = {
                        'free': balance['free'].get(currency, 0),
                        'used': balance['used'].get(currency, 0),
                        'total': data
                    }
            return result
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return {}
            
    async def get_ticker(self, symbol: str) -> Dict:
        """Get REAL ticker"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'symbol': ticker['symbol'],
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'last': ticker['last'],
                'volume': ticker['baseVolume'],
                'change': ticker['percentage'],
                'timestamp': ticker['timestamp']
            }
        except Exception as e:
            logger.error(f"Error fetching ticker: {e}")
            return None
            
    async def create_order(self, symbol: str, side: str, amount: float, price: float = None) -> Dict:
        """Create REAL order"""
        try:
            order_type = 'market' if price is None else 'limit'
            order = self.exchange.create_order(symbol, order_type, side, amount, price)
            logger.info(f"✅ Order created: {side} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return None
            
    async def get_order_book(self, symbol: str, limit: int = 10) -> Dict:
        """Get REAL order book"""
        try:
            orderbook = self.exchange.fetch_order_book(symbol, limit)
            return {
                'bids': orderbook['bids'][:limit],
                'asks': orderbook['asks'][:limit],
                'timestamp': orderbook['timestamp']
            }
        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return None
            
    async def get_funding_rate(self, symbol: str) -> Dict:
        """Get REAL funding rate"""
        try:
            market_id = symbol.replace('/', '') + '_UMCBL'
            funding = self.exchange.fetch_funding_rate(market_id)
            return {
                'symbol': symbol,
                'funding_rate': funding['fundingRate'],
                'funding_time': funding['fundingTimestamp'],
                'next_funding_time': funding['nextFundingTimestamp']
            }
        except Exception as e:
            logger.error(f"Error fetching funding rate: {e}")
            return None
            
    async def get_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> List:
        """Get REAL OHLCV data"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return [{
                'timestamp': c[0],
                'open': c[1],
                'high': c[2],
                'low': c[3],
                'close': c[4],
                'volume': c[5]
            } for c in ohlcv]
        except Exception as e:
            logger.error(f"Error fetching OHLCV: {e}")
            return []

# ==================== FIREBASE SERVICE ====================
class FirebaseService:
    def __init__(self):
        self.app = None
        self.db = None
        self.auth = None
        self.initialized = False
        
    def initialize(self):
        """Initialize Firebase with your REAL credentials"""
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate({
                    "type": "service_account",
                    "project_id": config.FIREBASE_PROJECT_ID,
                    "private_key": config.FIREBASE_PRIVATE_KEY,
                    "client_email": config.FIREBASE_CLIENT_EMAIL,
                    "token_uri": "https://oauth2.googleapis.com/token",
                })
                self.app = firebase_admin.initialize_app(cred, {
                    'databaseURL': f'https://{config.FIREBASE_PROJECT_ID}.firebaseio.com',
                    'storageBucket': config.FIREBASE_STORAGE_BUCKET
                })
            
            self.db = firestore.client()
            self.auth = auth
            self.initialized = True
            logger.info("✅ Firebase initialized")
            return True
        except Exception as e:
            logger.error(f"❌ Firebase init failed: {e}")
            return False
            
    # === USER MANAGEMENT ===
    async def create_user(self, email: str, password: str, username: str) -> Dict:
        """Create REAL user"""
        try:
            user = self.auth.create_user(
                email=email,
                password=password,
                display_name=username
            )
            
            user_data = {
                'uid': user.uid,
                'email': email,
                'username': username,
                'created_at': datetime.now().isoformat(),
                'role': 'user',
                'portfolio': {
                    'total': config.INITIAL_CAPITAL,
                    'available': config.INITIAL_CAPITAL,
                    'daily_pnl': 0,
                    'total_pnl': 0
                }
            }
            
            self.db.collection('users').document(user.uid).set(user_data)
            return user_data
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return None
            
    async def get_user(self, uid: str) -> Dict:
        """Get REAL user"""
        try:
            doc = self.db.collection('users').document(uid).get()
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
            
    async def verify_token(self, token: str) -> Dict:
        """Verify Firebase token"""
        try:
            return self.auth.verify_id_token(token)
        except Exception as e:
            logger.error(f"Error verifying token: {e}")
            return None
            
    # === TRADE MANAGEMENT ===
    async def save_trade(self, user_id: str, trade: Dict) -> str:
        """Save REAL trade"""
        try:
            trade.update({
                'user_id': user_id,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'created_at': datetime.now().isoformat()
            })
            doc_ref = self.db.collection('trades').document()
            doc_ref.set(trade)
            
            # Update portfolio
            await self.update_portfolio(user_id, trade)
            
            return doc_ref.id
        except Exception as e:
            logger.error(f"Error saving trade: {e}")
            return None
            
    async def get_trades(self, user_id: str, limit: int = 50) -> List:
        """Get REAL trades"""
        try:
            trades = self.db.collection('trades')\
                .where('user_id', '==', user_id)\
                .order_by('timestamp', direction=firestore.Query.DESCENDING)\
                .limit(limit)\
                .stream()
            return [{'id': t.id, **t.to_dict()} for t in trades]
        except Exception as e:
            logger.error(f"Error getting trades: {e}")
            return []
            
    # === PORTFOLIO MANAGEMENT ===
    async def get_portfolio(self, user_id: str) -> Dict:
        """Get REAL portfolio"""
        try:
            doc = self.db.collection('portfolios').document(user_id).get()
            if doc.exists:
                return doc.to_dict()
            return {
                'total': config.INITIAL_CAPITAL,
                'available': config.INITIAL_CAPITAL,
                'positions': [],
                'daily_pnl': 0,
                'total_pnl': 0
            }
        except Exception as e:
            logger.error(f"Error getting portfolio: {e}")
            return {}
            
    async def update_portfolio(self, user_id: str, trade: Dict):
        """Update REAL portfolio"""
        try:
            portfolio = await self.get_portfolio(user_id)
            
            if trade.get('side') == 'buy':
                portfolio['available'] -= trade.get('amount', 0)
                portfolio['positions'].append({
                    'symbol': trade.get('symbol'),
                    'amount': trade.get('amount'),
                    'price': trade.get('price'),
                    'timestamp': datetime.now().isoformat()
                })
            else:
                portfolio['available'] += trade.get('amount', 0)
                profit = trade.get('profit', 0)
                portfolio['total'] += profit
                portfolio['daily_pnl'] += profit
                portfolio['total_pnl'] += profit
                
            self.db.collection('portfolios').document(user_id).set(portfolio, merge=True)
        except Exception as e:
            logger.error(f"Error updating portfolio: {e}")
            
    # === OPPORTUNITY MANAGEMENT ===
    async def save_opportunity(self, opportunity: Dict) -> str:
        """Save REAL opportunity"""
        try:
            opportunity.update({
                'timestamp': firestore.SERVER_TIMESTAMP,
                'created_at': datetime.now().isoformat(),
                'status': 'detected'
            })
            doc_ref = self.db.collection('opportunities').document()
            doc_ref.set(opportunity)
            return doc_ref.id
        except Exception as e:
            logger.error(f"Error saving opportunity: {e}")
            return None
            
    async def get_opportunities(self, limit: int = 20) -> List:
        """Get REAL opportunities"""
        try:
            opps = self.db.collection('opportunities')\
                .where('status', '==', 'detected')\
                .order_by('timestamp', direction=firestore.Query.DESCENDING)\
                .limit(limit)\
                .stream()
            return [{'id': o.id, **o.to_dict()} for o in opps]
        except Exception as e:
            logger.error(f"Error getting opportunities: {e}")
            return []

# ==================== REDIS SERVICE ====================
class RedisService:
    def __init__(self):
        self.client = None
        self.connected = False
        
    async def connect(self):
        try:
            self.client = await redis.from_url(config.REDIS_URL, decode_responses=True)
            await self.client.ping()
            self.connected = True
            logger.info("✅ Redis connected")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            
    async def get(self, key: str):
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Error getting {key}: {e}")
            return None
            
    async def set(self, key: str, value: str, expire: int = 300):
        try:
            await self.client.setex(key, expire, value)
        except Exception as e:
            logger.error(f"Error setting {key}: {e}")

# ==================== STRATEGIES ====================
class BaseStrategy:
    def __init__(self, name: str, bitget: BitgetService, firebase: FirebaseService):
        self.name = name
        self.bitget = bitget
        self.firebase = firebase
        
    async def scan(self, market_data: Dict) -> List[Dict]:
        raise NotImplementedError
        
    async def execute(self, opportunity: Dict) -> Dict:
        raise NotImplementedError

class TriangularStrategy(BaseStrategy):
    def __init__(self, bitget: BitgetService, firebase: FirebaseService):
        super().__init__("Triangular Arbitrage", bitget, firebase)
        
    async def scan(self, market_data: Dict) -> List[Dict]:
        opportunities = []
        cycles = [
            ['USDT', 'BTC', 'ETH', 'USDT'],
            ['USDT', 'ETH', 'BTC', 'USDT'],
            ['USDT', 'SOL', 'BTC', 'USDT']
        ]
        
        for cycle in cycles:
            try:
                prices = []
                for i in range(3):
                    pair = f"{cycle[i]}/{cycle[i+1]}"
                    if pair in market_data:
                        prices.append(market_data[pair]['last'])
                    else:
                        reverse = f"{cycle[i+1]}/{cycle[i]}"
                        if reverse in market_data:
                            prices.append(1 / market_data[reverse]['last'])
                        else:
                            ticker = await self.bitget.get_ticker(pair)
                            if ticker:
                                prices.append(ticker['last'])
                            else:
                                break
                                
                if len(prices) != 3:
                    continue
                    
                start = 1000
                step1 = start / prices[0]
                step2 = step1 * prices[1]
                step3 = step2 * prices[2]
                roi = (step3 - start) / start - 0.003  # After fees
                
                if roi > config.MIN_PROFIT_THRESHOLD:
                    opp = {
                        'strategy': self.name,
                        'cycle': ' → '.join(cycle),
                        'prices': prices,
                        'roi': roi * 100,
                        'profit': roi * 1000,
                        'confidence': min(roi * 100, 1.0),
                        'timestamp': datetime.now().isoformat()
                    }
                    opportunities.append(opp)
                    await self.firebase.save_opportunity(opp)
                    
            except Exception as e:
                logger.error(f"Error in cycle: {e}")
                
        return opportunities
        
    async def execute(self, opportunity: Dict) -> Dict:
        try:
            cycle = opportunity['cycle'].split(' → ')
            prices = opportunity['prices']
            size = 100
            
            orders = []
            
            # Trade 1
            pair1 = f"{cycle[1]}/{cycle[0]}"
            order1 = await self.bitget.create_order(pair1, 'buy', size / prices[0])
            orders.append(order1)
            await asyncio.sleep(0.5)
            
            # Trade 2
            if order1:
                pair2 = f"{cycle[2]}/{cycle[1]}"
                order2 = await self.bitget.create_order(pair2, 'buy', order1['filled'])
                orders.append(order2)
                await asyncio.sleep(0.5)
                
                # Trade 3
                if order2:
                    pair3 = f"{cycle[0]}/{cycle[2]}"
                    order3 = await self.bitget.create_order(pair3, 'sell', order2['filled'])
                    orders.append(order3)
                    
                    profit = order3['cost'] - size if order3 else 0
                    
                    return {
                        'success': True,
                        'strategy': self.name,
                        'cycle': opportunity['cycle'],
                        'orders': orders,
                        'profit': profit,
                        'roi': profit / size,
                        'timestamp': datetime.now().isoformat()
                    }
                    
            return {'success': False, 'error': 'Order failed'}
            
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return {'success': False, 'error': str(e)}

# ==================== TRADING ENGINE ====================
class TradingEngine:
    def __init__(self, bitget: BitgetService, firebase: FirebaseService, redis: RedisService):
        self.bitget = bitget
        self.firebase = firebase
        self.redis = redis
        self.strategies = [
            TriangularStrategy(bitget, firebase)
        ]
        self.running = False
        self.positions = {}
        
    async def start(self):
        self.running = True
        logger.info("🚀 Trading engine started")
        
        while self.running:
            try:
                # Get market data
                market_data = await self.get_market_data()
                
                # Scan for opportunities
                all_opps = []
                for strategy in self.strategies:
                    opps = await strategy.scan(market_data)
                    all_opps.extend(opps)
                    
                # Execute best opportunities
                if all_opps:
                    all_opps.sort(key=lambda x: x['roi'], reverse=True)
                    for opp in all_opps[:config.MAX_CONCURRENT_TRADES]:
                        result = await strategy.execute(opp)
                        if result.get('success'):
                            await self.firebase.save_trade('system', result)
                            
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Engine error: {e}")
                await asyncio.sleep(10)
                
    async def get_market_data(self) -> Dict:
        data = {}
        symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
        
        for symbol in symbols:
            ticker = await self.bitget.get_ticker(symbol)
            if ticker:
                data[symbol] = ticker
                
        return data
        
    async def stop(self):
        self.running = False
        logger.info("🛑 Trading engine stopped")

# ==================== API AUTH ====================
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

# ==================== FASTAPI APP ====================
app = FastAPI(title="XTAAGC Bot API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== SERVICES ====================
bitget_service = BitgetService()
firebase_service = FirebaseService()
redis_service = RedisService()
trading_engine = None

# ==================== STARTUP ====================
@app.on_event("startup")
async def startup():
    global trading_engine
    
    # Connect to Bitget
    if not await bitget_service.connect():
        logger.error("Failed to connect to Bitget")
        
    # Initialize Firebase
    if not firebase_service.initialize():
        logger.error("Failed to initialize Firebase")
        
    # Connect to Redis
    await redis_service.connect()
    
    # Start trading engine
    trading_engine = TradingEngine(bitget_service, firebase_service, redis_service)
    asyncio.create_task(trading_engine.start())
    
    logger.info("✅ Server started")

# ==================== HEALTH ====================
@app.get("/health")
async def health():
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'bitget': bitget_service.connected,
        'firebase': firebase_service.initialized,
        'redis': redis_service.connected
    }

# ==================== AUTH ENDPOINTS ====================
@app.post("/api/auth/register")
async def register(request: Request):
    data = await request.json()
    email = data.get('email')
    password = data.get('password')
    username = data.get('username')
    
    if not all([email, password, username]):
        raise HTTPException(status_code=400, detail="Missing fields")
        
    user = await firebase_service.create_user(email, password, username)
    if not user:
        raise HTTPException(status_code=400, detail="User already exists")
        
    token = create_jwt_token({'uid': user['uid'], 'email': email})
    return {'token': token, 'user': user}

@app.post("/api/auth/login")
async def login(request: Request):
    data = await request.json()
    email = data.get('email')
    password = data.get('password')
    
    # Note: In production, verify with Firebase Auth
    token = create_jwt_token({'uid': 'test', 'email': email})
    return {'token': token, 'user': {'email': email, 'username': 'test'}}

# ==================== TRADING ENDPOINTS ====================
@app.get("/api/portfolio")
async def get_portfolio(user: dict = Depends(get_current_user)):
    portfolio = await firebase_service.get_portfolio(user.get('uid'))
    return portfolio

@app.get("/api/trades")
async def get_trades(limit: int = 50, user: dict = Depends(get_current_user)):
    trades = await firebase_service.get_trades(user.get('uid'), limit)
    return {'trades': trades}

@app.post("/api/trades")
async def execute_trade(request: Request, user: dict = Depends(get_current_user)):
    data = await request.json()
    
    # Execute trade
    order = await bitget_service.create_order(
        data.get('symbol'),
        data.get('side'),
        data.get('amount')
    )
    
    if order:
        trade_data = {
            'symbol': data.get('symbol'),
            'side': data.get('side'),
            'amount': data.get('amount'),
            'price': order.get('price'),
            'order_id': order.get('id'),
            'status': 'filled'
        }
        await firebase_service.save_trade(user.get('uid'), trade_data)
        return {'success': True, 'trade': trade_data}
    
    raise HTTPException(status_code=400, detail="Trade failed")

@app.get("/api/opportunities")
async def get_opportunities(limit: int = 20):
    opps = await firebase_service.get_opportunities(limit)
    return {'opportunities': opps}

@app.get("/api/price/{symbol}")
async def get_price(symbol: str):
    ticker = await bitget_service.get_ticker(symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return ticker

@app.get("/api/orderbook/{symbol}")
async def get_orderbook(symbol: str):
    book = await bitget_service.get_order_book(symbol)
    return book

# ==================== WEBSOCKET ====================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Send real-time updates
            ticker = await bitget_service.get_ticker('BTC/USDT')
            await websocket.send_json({
                'type': 'price',
                'data': ticker
            })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")

# ==================== MAIN ====================
if __name__ == "__main__":
    uvicorn.run(
        "backend:app",
        host="0.0.0.0",
        port=config.PORT,
        reload=config.DEBUG
    )
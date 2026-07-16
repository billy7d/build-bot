//+------------------------------------------------------------------+
//| Mentor_RSI_MTF_v1.mq5                                            |
//| RSI multi-timeframe EA with safer risk, armed setup, diagnostics. |
//| Compile and backtest in MetaTrader 5 before any live use.        |
//+------------------------------------------------------------------+
#property strict

#include <Trade/Trade.mqh>

CTrade trade;

enum EntryModeType
{
   RSI_CROSS_EMA = 0,
   RSI_ABOVE_EMA_AFTER_EXTREME = 1,
   RSI_PULLBACK_CONTINUATION = 2,
   RSI_FAN_STRUCTURE = 3
};

enum FanEntrySelectionType
{
   FAN_FIRST_VALID = 0,
   FAN_ENTRY1_ONLY = 1,
   FAN_ENTRY2_ONLY = 2,
   FAN_ENTRY3_ONLY = 3
};

enum FanEntryPointType
{
   FAN_ENTRY_NONE = 0,
   FAN_ENTRY1 = 1,
   FAN_ENTRY2 = 2,
   FAN_ENTRY3 = 3
};

enum FanPhaseType
{
   FAN_IDLE = 0,
   FAN_WAIT_FIRST_CROSS = 1,
   FAN_WAIT_RETEST = 2,
   FAN_WAIT_CONFIRM = 3,
   FAN_WAIT_ENTRY2 = 4,
   FAN_WAIT_ENTRY3 = 5,
   FAN_COMPLETE = 6
};

enum BiasModeType
{
   STRICT_COUNT = 0,
   HTF_VETO = 1
};

enum RegimeGateModeType
{
   REGIME_GATE_OFF = 0,
   REGIME_D1_EARLY_VETO = 1,
   REGIME_D1_H4_COMPOSITE_VETO = 2
};

enum TrailModeType
{
   TRAIL_OFF = 0,
   ATR_CHANDELIER = 1
};

enum PyramidAccountModeType
{
   PYRAMID_AUTO = 0,
   PYRAMID_NETTING = 1,
   PYRAMID_HEDGING_GROUP = 2
};

input ENUM_TIMEFRAMES EntryTF = PERIOD_M15;
input double RiskPerTradePct = 0.50;
input int MagicNumber = 26062901;
input int RSIPeriod = 14;
input int RSI_EMA_Period = 9;
input int RSI_WMA_Period = 45;
input double Oversold = 30.0;
input double Overbought = 70.0;
input double LongArmLevel = 35.0;
input double ShortArmLevel = 65.0;
input int LookbackExtremeBars = 24;
input int MaxSetupAgeBars = 48;
input int MaxBarsAfterCross = 5;
input double PullbackLongLevel = 50.0;
input double PullbackShortLevel = 50.0;
input int PullbackLookbackBars = 24;
input int MinAlignedTimeframes = 2;
input EntryModeType EntryMode = RSI_ABOVE_EMA_AFTER_EXTREME;
input BiasModeType BiasMode = HTF_VETO;
input RegimeGateModeType RegimeGateMode = REGIME_GATE_OFF;

// RSI fan structure: RSI, EMA9-RSI and WMA45-RSI converge, expand, then confirm a reversal.
input FanEntrySelectionType FanEntrySelection = FAN_FIRST_VALID;
input int FanOriginCrossWindowBars = 12;
input double FanOriginMaxSpread = 3.0;
input double FanMinExpansion = 4.0;
input double FanMinHigherLowRSI = 1.5;
input int FanMaxAgeBars = 72;
input int FanEntry2MinBarsAfterEntry1 = 1;
input bool FanAllowDirectWMAEntry = true;

input bool UseMTFBias = true;

input bool UseVolumeFilter = false;
input double VolumeSpikeMultiplier = 1.8;
input int VolumeMAPeriod = 20;

input bool UseChopFilter = true;
input double ChopMinRSI = 45.0;
input double ChopMaxRSI = 65.0;
input double ChopMAProximity = 2.0;

input int SwingLookbackBars = 10;
input double SLBufferPoints = 50;
input double MinRR = 1.20;
input double TP1_R = 1.0;
input double TP2_R = 2.0;
input double BreakEvenTriggerR = 1.0;
input double TP1ClosePct = 50.0;
input double TP2ClosePct = 25.0;
input bool UsePartialExits = true;
input bool UseHardTP2 = false;
input TrailModeType TrailMode = ATR_CHANDELIER;
input int ATRPeriod = 14;
input int TrailLookbackBars = 22;
input double TrailATRMultiplier = 3.0;
input double StartTrailingAfterR = 1.5;
input double RunnerMinPct = 25.0;

// Optional directional exit profile. Disabled by default to preserve baseline behavior.
input bool UseDirectionalExitProfile = false;
input double LongTP1_R = 1.0;
input double ShortTP1_R = 1.0;
input double LongBreakEvenTriggerR = 1.0;
input double ShortBreakEvenTriggerR = 1.0;
input double LongStartTrailingAfterR = 1.5;
input double ShortStartTrailingAfterR = 1.5;
input double LongTrailATRMultiplier = 3.0;
input double ShortTrailATRMultiplier = 3.0;
input double LongTP2RSILevel = 65.0;
input double ShortTP2RSILevel = 35.0;
input double LongH4ExitRSILevel = 70.0;
input double ShortH4ExitRSILevel = 30.0;
input bool UseShortInvalidationExit = false;
input double ShortInvalidationRSILevel = 50.0;
input double ShortInvalidationMaxR = 0.25;
input bool AllowLong = true;
input bool AllowShort = true;

// Optional long-side quality gates. Disabled by default to preserve baseline behavior.
input bool UseLongQualityFilter = false;
input bool LongRequireD1OrH4Bull = false;
input bool LongRequireH4Bull = false;
input double LongEntryRSIMax = 100.0;
input double LongH4RSIMin = 0.0;
input bool UseShortQualityFilter = false;
input bool ShortRequireD1OrH4Bear = false;
input bool ShortRequireH4Bear = false;
input double ShortEntryRSIMin = 0.0;
input double ShortH4RSIMax = 100.0;

// Profit-funded pyramiding. Disabled unless explicitly tested.
input bool UsePyramiding = false;
input PyramidAccountModeType PyramidAccountMode = PYRAMID_AUTO;
input int MaxPyramidAdds = 2;
input double Add1TriggerR = 2.0;
input double Add1RiskR = 0.30;
input double Add1LockFloorR = 0.75;
input double Add2TriggerR = 3.5;
input double Add2RiskR = 0.15;
input double Add2LockFloorR = 1.75;
input double PyramidCostReserveR = 0.15;
input double PyramidMinLockedProfitR = 0.10;
input int PyramidMinBarsBetweenAdds = 4;
input double PyramidMaxSpreadR = 0.10;
input double PyramidDisableAtEquityDDPct = 8.0;
input double PyramidMinMarginLevelPct = 500.0;
input double PyramidLongRSIMax = 68.0;
input double PyramidShortRSIMin = 32.0;
input bool Diagnostics = true;
input int DiagnosticsEveryBars = 12;
input bool ExportDiagnosticsCsv = false;

enum BiasState
{
   BIAS_BEAR = -1,
   BIAS_NEUTRAL = 0,
   BIAS_BULL = 1
};

struct TFState
{
   ENUM_TIMEFRAMES tf;
   double rsi1;
   double rsi2;
   double ema1;
   double ema2;
   double wma1;
   double wma2;
   double atr1;
   bool crossRSIUpEMA;
   bool crossRSIDownEMA;
   bool crossRSIUpWMA;
   bool crossRSIDownWMA;
   bool crossEMAUpWMA;
   bool crossEMADownWMA;
   bool extremeLowRecent;
   bool extremeHighRecent;
   bool pullbackLongRecent;
   bool pullbackShortRecent;
   bool chop;
   bool volumeSpike;
   BiasState bias;
};

struct RiskPlan
{
   double lots;
   double rawLots;
   double desiredRiskMoney;
   double actualRiskMoney;
   double actualRiskPct;
   double riskPerLot;
   string reason;
};

struct PyramidLeg
{
   ulong ticket;
   long identifier;
   double entryPrice;
   double volume;
   ENUM_ORDER_TYPE type;
};

struct FanTracker
{
   FanPhaseType phase;
   int ageBars;
   int barsSinceEntry1;
   double firstSwing;
   double retestSwing;
   double entry1RSI;
   double maxSpan;
   FanEntryPointType pendingSignal;
   bool consumed;
};

ENUM_TIMEFRAMES DataTFs[4] = { PERIOD_D1, PERIOD_H4, PERIOD_H1, PERIOD_M15 };
int rsiHandles[4];
int atrHandles[4];

datetime lastEntryBarTime = 0;
ulong managedTicket = 0;
bool tp1Done = false;
bool tp2Done = false;
double initialPositionVolume = 0.0;
double managedInitialRiskDistance = 0.0;

PyramidLeg pyramidLegs[];
PyramidAccountModeType activePyramidAccountMode = PYRAMID_NETTING;
bool pyramidCycleActive = false;
bool pyramidRecoveredPosition = false;
int pyramidAddCount = 0;
datetime pyramidLastAddBarTime = 0;
double pyramidBaseEntry = 0.0;
double pyramidInitialRiskDistance = 0.0;
double pyramidBaseRiskMoney = 0.0;
double pyramidRealizedNetProfit = 0.0;
double pyramidPeakEquity = 0.0;

int armedLongBars = 0;
int armedShortBars = 0;
int longFanOriginRSIWmaAge = 100000;
int shortFanOriginRSIWmaAge = 100000;
FanTracker longFan;
FanTracker shortFan;

int diagArmedLong = 0;
int diagArmedShort = 0;
int diagRejectBias = 0;
int diagRejectChop = 0;
int diagRejectRisk = 0;
int diagRejectCurl = 0;
int diagRejectCross = 0;
int diagRejectEMASide = 0;
int diagRejectVolume = 0;
int diagRejectLongQuality = 0;
int diagRejectShortQuality = 0;
int diagRejectRegimeLong = 0;
int diagRejectRegimeShort = 0;
int diagRejectFan = 0;
int diagFanLongOrigins = 0;
int diagFanShortOrigins = 0;
int diagFanExpired = 0;
int diagFanInvalid = 0;
int diagFanLongE1Signals = 0;
int diagFanLongE2Signals = 0;
int diagFanLongE3Signals = 0;
int diagFanShortE1Signals = 0;
int diagFanShortE2Signals = 0;
int diagFanShortE3Signals = 0;
int diagFanLongE1Opened = 0;
int diagFanLongE2Opened = 0;
int diagFanLongE3Opened = 0;
int diagFanShortE1Opened = 0;
int diagFanShortE2Opened = 0;
int diagFanShortE3Opened = 0;
int diagTrailExit = 0;
int diagLongTP1 = 0;
int diagShortTP1 = 0;
int diagLongTP2 = 0;
int diagShortTP2 = 0;
int diagLongH4Exit = 0;
int diagShortH4Exit = 0;
int diagShortInvalidationExit = 0;
int diagLongTrailUpdates = 0;
int diagShortTrailUpdates = 0;
int diagEntryBars = 0;
int diagTradesOpened = 0;
int diagLongOpened = 0;
int diagShortOpened = 0;
int diagRegimeLongOpenBull = 0;
int diagRegimeLongOpenNeutral = 0;
int diagRegimeLongOpenBear = 0;
int diagRegimeShortOpenBull = 0;
int diagRegimeShortOpenNeutral = 0;
int diagRegimeShortOpenBear = 0;
int diagPyramidCycles = 0;
int diagPyramidAdd1Opened = 0;
int diagPyramidAdd2Opened = 0;
int diagPyramidSkipMinLot = 0;
int diagPyramidSkipLockedPnl = 0;
int diagPyramidSkipSpread = 0;
int diagPyramidSkipMargin = 0;
int diagPyramidStopModifyFail = 0;
int diagPyramidStopModifySkip = 0;
int diagPyramidPostFillViolation = 0;
double diagPyramidWorstBundleStopPnLR = 0.0;
int diagCsvHandle = INVALID_HANDLE;

int TfIndex(ENUM_TIMEFRAMES tf)
{
   for(int i = 0; i < 4; i++)
      if(DataTFs[i] == tf)
         return i;
   return -1;
}

string TFName(ENUM_TIMEFRAMES tf)
{
   return EnumToString(tf);
}

int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);
   pyramidPeakEquity = AccountInfoDouble(ACCOUNT_EQUITY);

   long accountMarginMode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   bool accountIsHedging = (accountMarginMode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   activePyramidAccountMode = PyramidAccountMode;
   if(PyramidAccountMode == PYRAMID_AUTO)
      activePyramidAccountMode = accountIsHedging ? PYRAMID_HEDGING_GROUP : PYRAMID_NETTING;

   if(UsePyramiding)
   {
      if(activePyramidAccountMode == PYRAMID_NETTING && accountIsHedging)
      {
         Print("PyramidAccountMode=PYRAMID_NETTING cannot run on a hedging account. Use PYRAMID_AUTO or PYRAMID_HEDGING_GROUP.");
         return INIT_PARAMETERS_INCORRECT;
      }
      if(activePyramidAccountMode == PYRAMID_HEDGING_GROUP && !accountIsHedging)
      {
         Print("PyramidAccountMode=PYRAMID_HEDGING_GROUP requires a hedging account. Use PYRAMID_AUTO or PYRAMID_NETTING.");
         return INIT_PARAMETERS_INCORRECT;
      }

      if(MaxPyramidAdds < 1 || MaxPyramidAdds > 2 ||
         Add1TriggerR <= 0.0 || Add1RiskR <= 0.0 || Add1LockFloorR < 0.0 ||
         Add2TriggerR <= Add1TriggerR || Add2RiskR <= 0.0 || Add2LockFloorR < Add1LockFloorR ||
         PyramidCostReserveR < 0.0 || PyramidMinLockedProfitR < 0.0 ||
         PyramidMinBarsBetweenAdds < 0 || PyramidMaxSpreadR <= 0.0 ||
         PyramidDisableAtEquityDDPct < 0.0 || PyramidMinMarginLevelPct <= 0.0)
      {
         Print("Invalid pyramiding parameters.");
         return INIT_PARAMETERS_INCORRECT;
      }

      Print("PYRAMID account mode input=", PyramidAccountModeText(PyramidAccountMode),
            " active=", PyramidAccountModeText(activePyramidAccountMode));
   }

   for(int i = 0; i < 4; i++)
   {
      rsiHandles[i] = iRSI(_Symbol, DataTFs[i], RSIPeriod, PRICE_CLOSE);
      atrHandles[i] = iATR(_Symbol, DataTFs[i], ATRPeriod);

      if(rsiHandles[i] == INVALID_HANDLE || atrHandles[i] == INVALID_HANDLE)
      {
         Print("Failed to create core indicator handles for ", TFName(DataTFs[i]));
         return INIT_FAILED;
      }
   }

   if(TfIndex(EntryTF) < 0)
   {
      Print("EntryTF must be M15 or H1 for this EA version.");
      return INIT_FAILED;
   }

   if(MaxSetupAgeBars < 1 || LookbackExtremeBars < 1 || PullbackLookbackBars < 1)
   {
      Print("LookbackExtremeBars, MaxSetupAgeBars, and PullbackLookbackBars must be positive.");
      return INIT_FAILED;
   }

   if(LongEntryRSIMax < 0.0 || LongEntryRSIMax > 100.0 || LongH4RSIMin < 0.0 || LongH4RSIMin > 100.0 ||
      ShortEntryRSIMin < 0.0 || ShortEntryRSIMin > 100.0 || ShortH4RSIMax < 0.0 || ShortH4RSIMax > 100.0 ||
      LongTP2RSILevel < 0.0 || LongTP2RSILevel > 100.0 || ShortTP2RSILevel < 0.0 || ShortTP2RSILevel > 100.0 ||
      LongH4ExitRSILevel < 0.0 || LongH4ExitRSILevel > 100.0 || ShortH4ExitRSILevel < 0.0 || ShortH4ExitRSILevel > 100.0 ||
      ShortInvalidationRSILevel < 0.0 || ShortInvalidationRSILevel > 100.0)
   {
      Print("Quality RSI thresholds must be between 0 and 100.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(LongTP1_R <= 0.0 || ShortTP1_R <= 0.0 ||
      LongBreakEvenTriggerR <= 0.0 || ShortBreakEvenTriggerR <= 0.0 ||
      LongStartTrailingAfterR < 0.0 || ShortStartTrailingAfterR < 0.0 ||
      LongTrailATRMultiplier <= 0.0 || ShortTrailATRMultiplier <= 0.0 ||
      ShortInvalidationMaxR < 0.0)
   {
      Print("Directional exit R and ATR parameters are invalid.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(FanOriginCrossWindowBars < 1 || FanOriginMaxSpread <= 0.0 || FanMinExpansion < 0.0 ||
      FanMinHigherLowRSI < 0.0 || FanMaxAgeBars < 3 || FanEntry2MinBarsAfterEntry1 < 1)
   {
      Print("RSI fan structure parameters are invalid.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(ExportDiagnosticsCsv)
   {
      diagCsvHandle = FileOpen("Mentor_RSI_MTF_diag.csv", FILE_WRITE | FILE_CSV | FILE_ANSI);
      if(diagCsvHandle != INVALID_HANDLE)
      {
         FileWrite(diagCsvHandle, "time", "entry_tf", "entry_mode", "bias_mode", "armed_long", "armed_short",
                   "bias_bull", "bias_bear", "reject_bias", "reject_chop",
                   "reject_risk", "reject_curl", "reject_cross", "reject_ema_side",
                   "reject_volume", "reject_long_quality", "reject_short_quality", "regime_gate", "d1_regime_score",
                   "h4_regime_score", "composite_regime_score", "reject_regime_long", "reject_regime_short",
                   "pyramid_adds", "pyramid_skip_locked", "pyramid_skip_minlot",
                   "pyramid_skip_spread", "pyramid_skip_margin", "entry_state", "snapshot");
      }
      else
      {
         Print("Could not open Mentor_RSI_MTF_diag.csv for diagnostics export.");
      }
   }

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   PrintDiagnosticsSummary("OnDeinit");

   if(diagCsvHandle != INVALID_HANDLE)
   {
      FileClose(diagCsvHandle);
      diagCsvHandle = INVALID_HANDLE;
   }

   for(int i = 0; i < 4; i++)
   {
      if(rsiHandles[i] != INVALID_HANDLE)
         IndicatorRelease(rsiHandles[i]);
      if(atrHandles[i] != INVALID_HANDLE)
         IndicatorRelease(atrHandles[i]);
   }
}

double OnTester()
{
   PrintDiagnosticsSummary("OnTester");
   return 0.0;
}

void OnTick()
{
   UpdatePyramidPeakEquity();
   ManageOpenPosition();

   datetime barTime = iTime(_Symbol, EntryTF, 0);
   if(barTime == lastEntryBarTime)
      return;
   lastEntryBarTime = barTime;

   TFState fanEntry;
   ZeroMemory(fanEntry);
   bool fanStateReady = false;
   if(EntryMode == RSI_FAN_STRUCTURE)
   {
      if(!BuildState(EntryTF, fanEntry))
         return;
      UpdateFanStates(fanEntry);
      fanStateReady = true;
   }

   if(HasOpenPosition())
      return;

   TFState d1, h4, h1, m15, entry;
   if(!BuildState(PERIOD_D1, d1) || !BuildState(PERIOD_H4, h4) || !BuildState(PERIOD_H1, h1) || !BuildState(PERIOD_M15, m15))
      return;
   if(fanStateReady)
      entry = fanEntry;
   else if(!BuildState(EntryTF, entry))
      return;

   diagEntryBars++;
   if(EntryMode != RSI_FAN_STRUCTURE)
      UpdateArmedState(entry);

   int bullCount = 0;
   int bearCount = 0;
   CountBias(d1, bullCount, bearCount);
   CountBias(h4, bullCount, bearCount);
   CountBias(h1, bullCount, bearCount);

   bool longBias = BiasAllowsLong(d1, h4, h1, bullCount);
   bool shortBias = BiasAllowsShort(d1, h4, h1, bearCount);
   bool longRegime = RegimeAllowsLong(d1, h4);
   bool shortRegime = RegimeAllowsShort(d1, h4);

   string reject = "";
   if(AllowLong && LongSignal(entry, d1, h4, h1, longBias, longRegime, reject))
   {
      FanEntryPointType point = (EntryMode == RSI_FAN_STRUCTURE) ? FanSignal(true) : FAN_ENTRY_NONE;
      if(point != FAN_ENTRY_NONE)
         ConsumeFanSignal(true);
      OpenTrade(ORDER_TYPE_BUY, entry, d1, h4, h1, m15, point);
      if(EntryMode == RSI_FAN_STRUCTURE)
         return;
      if(HasOpenPosition())
         return;
   }
   else if(AllowLong && LongSetupActive(entry))
      TrackReject(reject);

   reject = "";
   if(AllowShort && ShortSignal(entry, d1, h4, h1, shortBias, shortRegime, reject))
   {
      FanEntryPointType point = (EntryMode == RSI_FAN_STRUCTURE) ? FanSignal(false) : FAN_ENTRY_NONE;
      if(point != FAN_ENTRY_NONE)
         ConsumeFanSignal(false);
      OpenTrade(ORDER_TYPE_SELL, entry, d1, h4, h1, m15, point);
   }
   else if(AllowShort && ShortSetupActive(entry))
      TrackReject(reject);

   PrintDiagnostics(d1, h4, h1, m15, entry, bullCount, bearCount);
}

bool BuildState(ENUM_TIMEFRAMES tf, TFState &s)
{
   int idx = TfIndex(tf);
   if(idx < 0)
      return false;

   const int need = 260;
   double rsi[];
   double atr[];
   MqlRates rates[];
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(atr, true);
   ArraySetAsSeries(rates, true);

   if(CopyBuffer(rsiHandles[idx], 0, 0, need, rsi) < need)
      return false;
   if(CopyBuffer(atrHandles[idx], 0, 0, need, atr) < need)
      return false;
   if(CopyRates(_Symbol, tf, 0, need, rates) < need)
      return false;

   s.tf = tf;
   s.rsi1 = rsi[1];
   s.rsi2 = rsi[2];
   s.ema1 = EMAOnSeries(rsi, RSI_EMA_Period, 1, need);
   s.ema2 = EMAOnSeries(rsi, RSI_EMA_Period, 2, need);
   s.wma1 = WMAOnSeries(rsi, RSI_WMA_Period, 1, need);
   s.wma2 = WMAOnSeries(rsi, RSI_WMA_Period, 2, need);
   s.atr1 = atr[1];
   s.crossRSIUpEMA = (s.rsi2 <= s.ema2 && s.rsi1 > s.ema1);
   s.crossRSIDownEMA = (s.rsi2 >= s.ema2 && s.rsi1 < s.ema1);
   s.crossRSIUpWMA = (s.rsi2 <= s.wma2 && s.rsi1 > s.wma1);
   s.crossRSIDownWMA = (s.rsi2 >= s.wma2 && s.rsi1 < s.wma1);
   s.crossEMAUpWMA = (s.ema2 <= s.wma2 && s.ema1 > s.wma1);
   s.crossEMADownWMA = (s.ema2 >= s.wma2 && s.ema1 < s.wma1);
   s.extremeLowRecent = RecentRSIExtreme(rsi, 1, LookbackExtremeBars, LongArmLevel, true);
   s.extremeHighRecent = RecentRSIExtreme(rsi, 1, LookbackExtremeBars, ShortArmLevel, false);
   s.pullbackLongRecent = RecentRSIExtreme(rsi, 1, PullbackLookbackBars, PullbackLongLevel, true);
   s.pullbackShortRecent = RecentRSIExtreme(rsi, 1, PullbackLookbackBars, PullbackShortLevel, false);
   s.chop = IsChop(s);
   s.volumeSpike = HasVolumeSpike(rates);
   s.bias = GetBias(s);
   return true;
}

double EMAOnSeries(const double &arr[], int period, int shift, int total)
{
   int oldest = MathMin(total - 1, shift + period * 4);
   double alpha = 2.0 / (period + 1.0);
   double ema = arr[oldest];

   for(int i = oldest - 1; i >= shift; i--)
      ema = alpha * arr[i] + (1.0 - alpha) * ema;

   return ema;
}

double WMAOnSeries(const double &arr[], int period, int shift, int total)
{
   if(shift + period >= total)
      return arr[shift];

   double weighted = 0.0;
   double weights = 0.0;
   for(int i = 0; i < period; i++)
   {
      double w = period - i;
      weighted += arr[shift + i] * w;
      weights += w;
   }
   return weighted / weights;
}

bool RecentRSIExtreme(const double &rsi[], int shift, int lookback, double level, bool lowExtreme)
{
   for(int i = shift; i < shift + lookback; i++)
   {
      if(lowExtreme && rsi[i] <= level)
         return true;
      if(!lowExtreme && rsi[i] >= level)
         return true;
   }
   return false;
}

void UpdateArmedState(const TFState &entry)
{
   if(entry.extremeLowRecent || entry.rsi1 <= LongArmLevel)
      armedLongBars = MaxSetupAgeBars;
   else if(armedLongBars > 0)
      armedLongBars--;

   if(entry.extremeHighRecent || entry.rsi1 >= ShortArmLevel)
      armedShortBars = MaxSetupAgeBars;
   else if(armedShortBars > 0)
      armedShortBars--;

   if(armedLongBars > 0)
      diagArmedLong++;
   if(armedShortBars > 0)
      diagArmedShort++;
}

double FanSpan(const TFState &entry)
{
   double high = MathMax(entry.rsi1, MathMax(entry.ema1, entry.wma1));
   double low = MathMin(entry.rsi1, MathMin(entry.ema1, entry.wma1));
   return high - low;
}

void ResetFanTracker(FanTracker &tracker)
{
   tracker.phase = FAN_IDLE;
   tracker.ageBars = 0;
   tracker.barsSinceEntry1 = 0;
   tracker.firstSwing = 0.0;
   tracker.retestSwing = 0.0;
   tracker.entry1RSI = 0.0;
   tracker.maxSpan = 0.0;
   tracker.pendingSignal = FAN_ENTRY_NONE;
   tracker.consumed = false;
}

void StartFanTracker(FanTracker &tracker, bool longSide, const TFState &entry)
{
   ResetFanTracker(tracker);
   tracker.phase = FAN_WAIT_FIRST_CROSS;
   tracker.firstSwing = entry.rsi1;
   tracker.retestSwing = entry.rsi1;
   tracker.maxSpan = FanSpan(entry);

   if(longSide)
      diagFanLongOrigins++;
   else
      diagFanShortOrigins++;
}

void RegisterFanSignal(bool longSide, FanEntryPointType point)
{
   if(point == FAN_ENTRY1)
   {
      if(longSide)
         diagFanLongE1Signals++;
      else
         diagFanShortE1Signals++;
   }
   else if(point == FAN_ENTRY2)
   {
      if(longSide)
         diagFanLongE2Signals++;
      else
         diagFanShortE2Signals++;
   }
   else if(point == FAN_ENTRY3)
   {
      if(longSide)
         diagFanLongE3Signals++;
      else
         diagFanShortE3Signals++;
   }

}

void EmitFanSignal(FanTracker &tracker, bool longSide, FanEntryPointType point)
{
   tracker.pendingSignal = point;
   RegisterFanSignal(longSide, point);
}

void AdvanceFanTracker(FanTracker &tracker, bool longSide, const TFState &entry)
{
   tracker.pendingSignal = FAN_ENTRY_NONE;
   if(tracker.phase == FAN_IDLE || tracker.phase == FAN_COMPLETE)
      return;

   tracker.ageBars++;
   if(tracker.ageBars > FanMaxAgeBars)
   {
      diagFanExpired++;
      ResetFanTracker(tracker);
      return;
   }

   tracker.maxSpan = MathMax(tracker.maxSpan, FanSpan(entry));
   if(tracker.consumed)
      return;

   bool crossEMA = longSide ? entry.crossRSIUpEMA : entry.crossRSIDownEMA;
   bool crossWMA = longSide ? entry.crossRSIUpWMA : entry.crossRSIDownWMA;
   bool movedBackAcrossEMA = longSide ? (entry.crossRSIDownEMA || entry.rsi1 <= entry.ema1)
                                       : (entry.crossRSIUpEMA || entry.rsi1 >= entry.ema1);
   bool expansionReady = (tracker.maxSpan >= FanMinExpansion);

   if(tracker.phase == FAN_WAIT_FIRST_CROSS)
   {
      if(longSide)
         tracker.firstSwing = MathMin(tracker.firstSwing, entry.rsi1);
      else
         tracker.firstSwing = MathMax(tracker.firstSwing, entry.rsi1);

      if(!expansionReady)
         return;

      if(FanAllowDirectWMAEntry && crossWMA)
      {
         EmitFanSignal(tracker, longSide, FAN_ENTRY3);
         tracker.phase = FAN_COMPLETE;
         return;
      }

      if(crossEMA)
      {
         tracker.phase = FAN_WAIT_RETEST;
         tracker.retestSwing = entry.rsi1;
      }
      return;
   }

   if(tracker.phase == FAN_WAIT_RETEST)
   {
      if(FanAllowDirectWMAEntry && crossWMA)
      {
         EmitFanSignal(tracker, longSide, FAN_ENTRY3);
         tracker.phase = FAN_COMPLETE;
         return;
      }

      if(movedBackAcrossEMA)
      {
         tracker.phase = FAN_WAIT_CONFIRM;
         tracker.retestSwing = entry.rsi1;
      }
      return;
   }

   if(tracker.phase == FAN_WAIT_CONFIRM)
   {
      if(longSide && entry.rsi1 <= entry.ema1)
         tracker.retestSwing = MathMin(tracker.retestSwing, entry.rsi1);
      else if(!longSide && entry.rsi1 >= entry.ema1)
         tracker.retestSwing = MathMax(tracker.retestSwing, entry.rsi1);

      if(FanAllowDirectWMAEntry && crossWMA)
      {
         EmitFanSignal(tracker, longSide, FAN_ENTRY3);
         tracker.phase = FAN_COMPLETE;
         return;
      }

      if(crossEMA)
      {
         bool higherLow = longSide ? (tracker.retestSwing >= tracker.firstSwing + FanMinHigherLowRSI)
                                   : (tracker.retestSwing <= tracker.firstSwing - FanMinHigherLowRSI);
         if(!higherLow)
         {
            diagFanInvalid++;
            ResetFanTracker(tracker);
            return;
         }

         tracker.entry1RSI = entry.rsi1;
         tracker.barsSinceEntry1 = 0;
         tracker.phase = FAN_WAIT_ENTRY2;
         EmitFanSignal(tracker, longSide, FAN_ENTRY1);
      }
      return;
   }

   if(tracker.phase == FAN_WAIT_ENTRY2)
   {
      tracker.barsSinceEntry1++;
      if(crossWMA)
      {
         EmitFanSignal(tracker, longSide, FAN_ENTRY3);
         tracker.phase = FAN_COMPLETE;
         return;
      }

      bool betweenAverages = longSide ? (entry.rsi1 > entry.ema1 && entry.rsi1 <= entry.wma1)
                                      : (entry.rsi1 < entry.ema1 && entry.rsi1 >= entry.wma1);
      bool passedEntry1 = longSide ? (entry.rsi1 > tracker.entry1RSI) : (entry.rsi1 < tracker.entry1RSI);
      if(tracker.barsSinceEntry1 >= FanEntry2MinBarsAfterEntry1 && betweenAverages && passedEntry1)
      {
         EmitFanSignal(tracker, longSide, FAN_ENTRY2);
         tracker.phase = FAN_WAIT_ENTRY3;
      }
      return;
   }

   if(tracker.phase == FAN_WAIT_ENTRY3 && crossWMA)
   {
      EmitFanSignal(tracker, longSide, FAN_ENTRY3);
      tracker.phase = FAN_COMPLETE;
   }
}

void UpdateFanStates(const TFState &entry)
{
   if(EntryMode != RSI_FAN_STRUCTURE)
      return;

   if(entry.crossRSIDownWMA)
      longFanOriginRSIWmaAge = 0;
   else if(longFanOriginRSIWmaAge < 100000)
      longFanOriginRSIWmaAge++;

   if(entry.crossRSIUpWMA)
      shortFanOriginRSIWmaAge = 0;
   else if(shortFanOriginRSIWmaAge < 100000)
      shortFanOriginRSIWmaAge++;

   bool longOrigin = (entry.crossEMADownWMA && longFanOriginRSIWmaAge >= 1 &&
                      longFanOriginRSIWmaAge <= FanOriginCrossWindowBars && FanSpan(entry) <= FanOriginMaxSpread);
   bool shortOrigin = (entry.crossEMAUpWMA && shortFanOriginRSIWmaAge >= 1 &&
                       shortFanOriginRSIWmaAge <= FanOriginCrossWindowBars && FanSpan(entry) <= FanOriginMaxSpread);

   if(longOrigin)
      StartFanTracker(longFan, true, entry);
   else
      AdvanceFanTracker(longFan, true, entry);

   if(shortOrigin)
      StartFanTracker(shortFan, false, entry);
   else
      AdvanceFanTracker(shortFan, false, entry);
}

bool FanTrackerIsActive(const FanTracker &tracker)
{
   return (!tracker.consumed && (tracker.pendingSignal != FAN_ENTRY_NONE ||
           (tracker.phase != FAN_IDLE && tracker.phase != FAN_COMPLETE)));
}

FanEntryPointType FanSignal(bool longSide)
{
   if(longSide)
   {
      if(longFan.consumed)
         return FAN_ENTRY_NONE;
      return longFan.pendingSignal;
   }

   if(shortFan.consumed)
      return FAN_ENTRY_NONE;
   return shortFan.pendingSignal;
}

bool FanSelectionAllows(FanEntryPointType point)
{
   if(point == FAN_ENTRY_NONE)
      return false;
   if(FanEntrySelection == FAN_FIRST_VALID)
      return true;
   if(FanEntrySelection == FAN_ENTRY1_ONLY)
      return (point == FAN_ENTRY1);
   if(FanEntrySelection == FAN_ENTRY2_ONLY)
      return (point == FAN_ENTRY2);
   return (point == FAN_ENTRY3);
}

void ConsumeFanSignal(bool longSide)
{
   if(longSide)
   {
      longFan.consumed = true;
      longFan.pendingSignal = FAN_ENTRY_NONE;
      longFan.phase = FAN_COMPLETE;
   }
   else
   {
      shortFan.consumed = true;
      shortFan.pendingSignal = FAN_ENTRY_NONE;
      shortFan.phase = FAN_COMPLETE;
   }
}

BiasState GetBias(const TFState &s)
{
   bool rsiBull = (s.rsi1 > s.ema1 && s.ema1 >= s.wma1 && s.wma1 >= s.wma2);
   bool rsiBear = (s.rsi1 < s.ema1 && s.ema1 <= s.wma1 && s.wma1 <= s.wma2);

   if(rsiBull)
      return BIAS_BULL;
   if(rsiBear)
      return BIAS_BEAR;

   return BIAS_NEUTRAL;
}

bool IsChop(const TFState &s)
{
   if(!UseChopFilter)
      return false;

   bool rsiMid = (s.rsi1 >= ChopMinRSI && s.rsi1 <= ChopMaxRSI);
   bool maTight = (MathAbs(s.ema1 - s.wma1) <= ChopMAProximity);
   return (rsiMid && maTight);
}

bool HasVolumeSpike(const MqlRates &rates[])
{
   if(!UseVolumeFilter)
      return true;

   double sum = 0.0;
   for(int i = 2; i < 2 + VolumeMAPeriod; i++)
      sum += (double)rates[i].tick_volume;

   double avg = sum / VolumeMAPeriod;
   return ((double)rates[1].tick_volume >= avg * VolumeSpikeMultiplier);
}

void CountBias(const TFState &s, int &bullCount, int &bearCount)
{
   if(s.bias == BIAS_BULL)
      bullCount++;
   if(s.bias == BIAS_BEAR)
      bearCount++;
}

bool BiasAllowsLong(const TFState &d1, const TFState &h4, const TFState &h1, int bullCount)
{
   if(!UseMTFBias)
      return true;

   if(BiasMode == STRICT_COUNT)
      return (bullCount >= MinAlignedTimeframes && h4.bias != BIAS_BEAR && d1.bias != BIAS_BEAR);

   return (d1.bias != BIAS_BEAR && h4.bias != BIAS_BEAR && (h4.bias == BIAS_BULL || h1.bias == BIAS_BULL));
}

bool BiasAllowsShort(const TFState &d1, const TFState &h4, const TFState &h1, int bearCount)
{
   if(!UseMTFBias)
      return true;

   if(BiasMode == STRICT_COUNT)
      return (bearCount >= MinAlignedTimeframes && h4.bias != BIAS_BULL && d1.bias != BIAS_BULL);

   return (d1.bias != BIAS_BULL && h4.bias != BIAS_BULL && (h4.bias == BIAS_BEAR || h1.bias == BIAS_BEAR));
}

int SignedComparison(double left, double right)
{
   if(left > right)
      return 1;
   if(left < right)
      return -1;
   return 0;
}

int RegimeScore(const TFState &state)
{
   int score = 0;
   score += SignedComparison(state.rsi1, state.wma1);
   score += SignedComparison(state.ema1, state.wma1);
   score += SignedComparison(state.ema1, state.ema2);
   score += SignedComparison(state.wma1, state.wma2);
   return score;
}

int CompositeRegimeScore(const TFState &d1, const TFState &h4)
{
   return 2 * RegimeScore(d1) + RegimeScore(h4);
}

BiasState RegimeBucket(const TFState &d1, const TFState &h4)
{
   int score = CompositeRegimeScore(d1, h4);
   if(score >= 4)
      return BIAS_BULL;
   if(score <= -4)
      return BIAS_BEAR;
   return BIAS_NEUTRAL;
}

string RegimeBucketCode(const TFState &d1, const TFState &h4)
{
   BiasState bucket = RegimeBucket(d1, h4);
   if(bucket == BIAS_BULL)
      return "B";
   if(bucket == BIAS_BEAR)
      return "S";
   return "N";
}

bool RegimeAllowsLong(const TFState &d1, const TFState &h4)
{
   if(RegimeGateMode == REGIME_GATE_OFF)
      return true;
   if(RegimeGateMode == REGIME_D1_EARLY_VETO)
      return (RegimeScore(d1) > -2);
   return (CompositeRegimeScore(d1, h4) > -4);
}

bool RegimeAllowsShort(const TFState &d1, const TFState &h4)
{
   if(RegimeGateMode == REGIME_GATE_OFF)
      return true;
   if(RegimeGateMode == REGIME_D1_EARLY_VETO)
      return (RegimeScore(d1) < 2);
   return (CompositeRegimeScore(d1, h4) < 4);
}

void TrackRegimeOpened(bool longSide, const TFState &d1, const TFState &h4)
{
   BiasState bucket = RegimeBucket(d1, h4);
   if(longSide)
   {
      if(bucket == BIAS_BULL)
         diagRegimeLongOpenBull++;
      else if(bucket == BIAS_BEAR)
         diagRegimeLongOpenBear++;
      else
         diagRegimeLongOpenNeutral++;
      return;
   }

   if(bucket == BIAS_BULL)
      diagRegimeShortOpenBull++;
   else if(bucket == BIAS_BEAR)
      diagRegimeShortOpenBear++;
   else
      diagRegimeShortOpenNeutral++;
}

bool LongQualityAllows(const TFState &entry, const TFState &d1, const TFState &h4, const TFState &h1)
{
   if(!UseLongQualityFilter)
      return true;

   if(LongEntryRSIMax < 100.0 && entry.rsi1 > LongEntryRSIMax)
      return false;
   if(LongH4RSIMin > 0.0 && h4.rsi1 < LongH4RSIMin)
      return false;
   if(LongRequireH4Bull && h4.bias != BIAS_BULL)
      return false;
   if(LongRequireD1OrH4Bull && d1.bias != BIAS_BULL && h4.bias != BIAS_BULL)
      return false;

   return true;
}

bool ShortQualityAllows(const TFState &entry, const TFState &d1, const TFState &h4, const TFState &h1)
{
   if(!UseShortQualityFilter)
      return true;

   if(ShortEntryRSIMin > 0.0 && entry.rsi1 < ShortEntryRSIMin)
      return false;
   if(ShortH4RSIMax < 100.0 && h4.rsi1 > ShortH4RSIMax)
      return false;
   if(ShortRequireH4Bear && h4.bias != BIAS_BEAR)
      return false;
   if(ShortRequireD1OrH4Bear && d1.bias != BIAS_BEAR && h4.bias != BIAS_BEAR)
      return false;

   return true;
}

bool LongSetupActive(const TFState &entry)
{
   if(EntryMode == RSI_FAN_STRUCTURE)
      return FanTrackerIsActive(longFan);
   if(EntryMode == RSI_PULLBACK_CONTINUATION)
      return (armedLongBars > 0 || entry.pullbackLongRecent);
   return (armedLongBars > 0);
}

bool ShortSetupActive(const TFState &entry)
{
   if(EntryMode == RSI_FAN_STRUCTURE)
      return FanTrackerIsActive(shortFan);
   if(EntryMode == RSI_PULLBACK_CONTINUATION)
      return (armedShortBars > 0 || entry.pullbackShortRecent);
   return (armedShortBars > 0);
}

bool LongSignal(const TFState &entry, const TFState &d1, const TFState &h4, const TFState &h1,
                bool biasOK, bool regimeOK, string &reject)
{
   if(!LongSetupActive(entry))
   {
      reject = "not_armed";
      return false;
   }
   if(!biasOK)
   {
      reject = "bias";
      return false;
   }
   if(!regimeOK)
   {
      reject = "regime_long";
      return false;
   }
   if(!LongQualityAllows(entry, d1, h4, h1))
   {
      reject = "long_quality";
      return false;
   }
   if(entry.chop)
   {
      reject = "chop";
      return false;
   }
   if(UseVolumeFilter && !entry.volumeSpike)
   {
      reject = "volume";
      return false;
   }
   bool curlUp = (entry.rsi1 > entry.rsi2);
   if(!curlUp)
   {
      reject = "curl";
      return false;
   }

   if(EntryMode == RSI_CROSS_EMA)
   {
      bool rsiCrossEMA = entry.crossRSIUpEMA || RSICrossEMAWithinBars(entry.tf, true, MaxBarsAfterCross);
      bool wmaConfirm = (entry.ema1 >= entry.wma1 || entry.crossEMAUpWMA);

      if(!rsiCrossEMA)
      {
         reject = "cross";
         return false;
      }

      if(wmaConfirm || entry.rsi1 > entry.ema1)
      {
         reject = "";
         return true;
      }

      reject = "cross";
      return false;
   }

   if(EntryMode == RSI_PULLBACK_CONTINUATION)
   {
      if(entry.rsi1 > entry.ema1 && entry.ema1 >= entry.ema2)
      {
         reject = "";
         return true;
      }

      reject = "ema_side";
      return false;
   }

   if(EntryMode == RSI_FAN_STRUCTURE)
   {
      if(FanSelectionAllows(FanSignal(true)))
      {
         reject = "";
         return true;
      }

      reject = "fan";
      return false;
   }

   if(entry.rsi1 > entry.ema1)
   {
      reject = "";
      return true;
   }

   reject = "ema_side";
   return false;
}

bool ShortSignal(const TFState &entry, const TFState &d1, const TFState &h4, const TFState &h1,
                 bool biasOK, bool regimeOK, string &reject)
{
   if(!ShortSetupActive(entry))
   {
      reject = "not_armed";
      return false;
   }
   if(!biasOK)
   {
      reject = "bias";
      return false;
   }
   if(!regimeOK)
   {
      reject = "regime_short";
      return false;
   }
   if(!ShortQualityAllows(entry, d1, h4, h1))
   {
      reject = "short_quality";
      return false;
   }
   if(entry.chop)
   {
      reject = "chop";
      return false;
   }
   if(UseVolumeFilter && !entry.volumeSpike)
   {
      reject = "volume";
      return false;
   }
   bool curlDown = (entry.rsi1 < entry.rsi2);
   if(!curlDown)
   {
      reject = "curl";
      return false;
   }

   if(EntryMode == RSI_CROSS_EMA)
   {
      bool rsiCrossEMA = entry.crossRSIDownEMA || RSICrossEMAWithinBars(entry.tf, false, MaxBarsAfterCross);
      bool wmaConfirm = (entry.ema1 <= entry.wma1 || entry.crossEMADownWMA);

      if(!rsiCrossEMA)
      {
         reject = "cross";
         return false;
      }

      if(wmaConfirm || entry.rsi1 < entry.ema1)
      {
         reject = "";
         return true;
      }

      reject = "cross";
      return false;
   }

   if(EntryMode == RSI_PULLBACK_CONTINUATION)
   {
      if(entry.rsi1 < entry.ema1 && entry.ema1 <= entry.ema2)
      {
         reject = "";
         return true;
      }

      reject = "ema_side";
      return false;
   }

   if(EntryMode == RSI_FAN_STRUCTURE)
   {
      if(FanSelectionAllows(FanSignal(false)))
      {
         reject = "";
         return true;
      }

      reject = "fan";
      return false;
   }

   if(entry.rsi1 < entry.ema1)
   {
      reject = "";
      return true;
   }

   reject = "ema_side";
   return false;
}

bool RSICrossEMAWithinBars(ENUM_TIMEFRAMES tf, bool up, int bars)
{
   int idx = TfIndex(tf);
   if(idx < 0)
      return false;

   double rsi[];
   ArraySetAsSeries(rsi, true);
   int need = 120;
   if(CopyBuffer(rsiHandles[idx], 0, 0, need, rsi) < need)
      return false;

   for(int shift = 1; shift <= bars + 1; shift++)
   {
      double emaA = EMAOnSeries(rsi, RSI_EMA_Period, shift, need);
      double emaB = EMAOnSeries(rsi, RSI_EMA_Period, shift + 1, need);

      if(up && rsi[shift + 1] <= emaB && rsi[shift] > emaA)
         return true;
      if(!up && rsi[shift + 1] >= emaB && rsi[shift] < emaA)
         return true;
   }
   return false;
}

bool IsHedgingPyramidMode()
{
   return (UsePyramiding && activePyramidAccountMode == PYRAMID_HEDGING_GROUP);
}

bool SelectedPositionIsManaged()
{
   return (PositionGetString(POSITION_SYMBOL) == _Symbol &&
           (int)PositionGetInteger(POSITION_MAGIC) == MagicNumber);
}

bool SelectManagedPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(SelectedPositionIsManaged())
         return true;
   }
   return false;
}

int CountManagedPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(SelectedPositionIsManaged())
         count++;
   }
   return count;
}

long PositionIdentifierByTicket(ulong ticket)
{
   if(ticket == 0 || !PositionSelectByTicket(ticket))
      return 0;
   return (long)PositionGetInteger(POSITION_IDENTIFIER);
}

ulong FindNewestManagedPositionTicket(string comment, long positionType, double expectedVolume)
{
   ulong bestTicket = 0;
   long bestTimeMsc = -1;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double tolerance = MathMax(step * 0.5, 0.0000001);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(!SelectedPositionIsManaged())
         continue;
      if((long)PositionGetInteger(POSITION_TYPE) != positionType)
         continue;
      if(comment != "" && PositionGetString(POSITION_COMMENT) != comment)
         continue;
      if(expectedVolume > 0.0 && MathAbs(PositionGetDouble(POSITION_VOLUME) - expectedVolume) > tolerance)
         continue;

      long timeMsc = (long)PositionGetInteger(POSITION_TIME_MSC);
      if(timeMsc > bestTimeMsc || (timeMsc == bestTimeMsc && ticket > bestTicket))
      {
         bestTimeMsc = timeMsc;
         bestTicket = ticket;
      }
   }

   if(bestTicket == 0 && comment != "")
      return FindNewestManagedPositionTicket("", positionType, expectedVolume);

   return bestTicket;
}

bool HasOpenPosition()
{
   return SelectManagedPosition();
}

void OpenTrade(ENUM_ORDER_TYPE type, const TFState &entry, const TFState &d1, const TFState &h4, const TFState &h1, const TFState &m15,
               FanEntryPointType fanEntryPoint = FAN_ENTRY_NONE)
{
   double price = (type == ORDER_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl = InitialSL(type);
   if(sl <= 0)
      return;

   double riskDistance = MathAbs(price - sl);
   if(riskDistance <= _Point)
      return;

   double tp = 0.0;
   if(UseHardTP2)
      tp = (type == ORDER_TYPE_BUY) ? price + riskDistance * TP2_R : price - riskDistance * TP2_R;
   double rr = TP2_R;
   if(rr < MinRR)
      return;

   RiskPlan rp;
   if(!BuildRiskPlan(riskDistance, rp))
   {
      diagRejectRisk++;
      Print("Skip trade risk. reason=", rp.reason,
            " desiredRisk=", DoubleToString(rp.desiredRiskMoney, 2),
            " actualRisk=", DoubleToString(rp.actualRiskMoney, 2),
            " actualRiskPct=", DoubleToString(rp.actualRiskPct, 2),
            " rawLots=", DoubleToString(rp.rawLots, 4),
            " minLot=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 2),
            " stopDistance=", DoubleToString(riskDistance, _Digits));
      return;
   }

   string comment = (type == ORDER_TYPE_BUY) ? "RSI_MTF_LONG" : "RSI_MTF_SHORT";
   if(fanEntryPoint != FAN_ENTRY_NONE)
      comment += "_FAN_" + FanPointText(fanEntryPoint);
   if(RegimeGateMode != REGIME_GATE_OFF)
      comment += "_RG_" + RegimeBucketCode(d1, h4);
   bool ok = false;
   if(type == ORDER_TYPE_BUY)
      ok = trade.Buy(rp.lots, _Symbol, price, sl, tp, comment);
   else
      ok = trade.Sell(rp.lots, _Symbol, price, sl, tp, comment);

   if(ok)
   {
      long openedPositionType = (type == ORDER_TYPE_BUY) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
      ulong positionTicket = FindNewestManagedPositionTicket(comment, openedPositionType, rp.lots);
      managedTicket = (positionTicket > 0) ? positionTicket : (ulong)trade.ResultOrder();
      tp1Done = false;
      tp2Done = false;
      initialPositionVolume = rp.lots;
      managedInitialRiskDistance = riskDistance;
      if(UsePyramiding)
      {
         double fillPrice = trade.ResultPrice();
         if(positionTicket > 0 && PositionSelectByTicket(positionTicket))
         {
            fillPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            initialPositionVolume = PositionGetDouble(POSITION_VOLUME);
         }
         else if(fillPrice <= 0.0 && SelectManagedPosition())
            fillPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         if(fillPrice > 0.0)
            StartPyramidCycle(type, fillPrice, initialPositionVolume, sl, positionTicket);
      }
      armedLongBars = 0;
      armedShortBars = 0;
      diagTradesOpened++;
      if(type == ORDER_TYPE_BUY)
         diagLongOpened++;
      else
         diagShortOpened++;
      TrackRegimeOpened(type == ORDER_TYPE_BUY, d1, h4);
      if(fanEntryPoint != FAN_ENTRY_NONE)
         TrackFanOpened(type == ORDER_TYPE_BUY, fanEntryPoint);
      Print(comment, " opened lots=", DoubleToString(rp.lots, 2),
            " desiredRisk=", DoubleToString(rp.desiredRiskMoney, 2),
            " actualRisk=", DoubleToString(rp.actualRiskMoney, 2),
            " actualRiskPct=", DoubleToString(rp.actualRiskPct, 2),
            " stopDistance=", DoubleToString(riskDistance, _Digits),
            " snapshot=", Snapshot(d1, h4, h1, m15));
   }
   else
      Print("Order failed: ", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
}

double InitialSL(ENUM_ORDER_TYPE type)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, EntryTF, 0, SwingLookbackBars + 3, rates) < SwingLookbackBars + 3)
      return 0.0;

   if(type == ORDER_TYPE_BUY)
   {
      double low = rates[1].low;
      for(int i = 2; i <= SwingLookbackBars; i++)
         low = MathMin(low, rates[i].low);
      return NormalizeDouble(low - SLBufferPoints * _Point, _Digits);
   }

   double high = rates[1].high;
   for(int i = 2; i <= SwingLookbackBars; i++)
      high = MathMax(high, rates[i].high);
   return NormalizeDouble(high + SLBufferPoints * _Point, _Digits);
}

bool BuildRiskPlan(double riskDistance, RiskPlan &rp)
{
   rp.lots = 0.0;
   rp.rawLots = 0.0;
   rp.desiredRiskMoney = 0.0;
   rp.actualRiskMoney = 0.0;
   rp.actualRiskPct = 0.0;
   rp.riskPerLot = 0.0;
   rp.reason = "";

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   rp.desiredRiskMoney = equity * RiskPerTradePct / 100.0;
   if(tickValue <= 0 || tickSize <= 0 || step <= 0)
   {
      rp.reason = "invalid_symbol_specs";
      return false;
   }

   rp.riskPerLot = riskDistance / tickSize * tickValue;
   if(rp.riskPerLot <= 0)
   {
      rp.reason = "invalid_risk_per_lot";
      return false;
   }

   rp.rawLots = rp.desiredRiskMoney / rp.riskPerLot;
   if(rp.rawLots < minLot)
   {
      rp.lots = minLot;
      rp.actualRiskMoney = rp.riskPerLot * minLot;
      rp.actualRiskPct = (equity > 0) ? rp.actualRiskMoney / equity * 100.0 : 0.0;
      rp.reason = "raw_lot_below_min_lot";
      return false;
   }

   rp.lots = MathFloor(rp.rawLots / step) * step;
   rp.lots = MathMin(maxLot, rp.lots);
   rp.lots = NormalizeDouble(rp.lots, 2);

   if(rp.lots < minLot)
   {
      rp.reason = "normalized_lot_below_min_lot";
      return false;
   }

   rp.actualRiskMoney = rp.riskPerLot * rp.lots;
   rp.actualRiskPct = (equity > 0) ? rp.actualRiskMoney / equity * 100.0 : 0.0;

   if(rp.actualRiskMoney > rp.desiredRiskMoney + 0.01)
   {
      rp.reason = "actual_risk_exceeds_desired";
      return false;
   }

   return true;
}

bool BuildRiskPlanForMoney(double riskDistance, double desiredRiskMoney, RiskPlan &rp)
{
   rp.lots = 0.0;
   rp.rawLots = 0.0;
   rp.desiredRiskMoney = desiredRiskMoney;
   rp.actualRiskMoney = 0.0;
   rp.actualRiskPct = 0.0;
   rp.riskPerLot = 0.0;
   rp.reason = "";

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(desiredRiskMoney <= 0.0 || tickValue <= 0.0 || tickSize <= 0.0 || step <= 0.0)
   {
      rp.reason = "invalid_add_risk_specs";
      return false;
   }

   rp.riskPerLot = riskDistance / tickSize * tickValue;
   if(rp.riskPerLot <= 0.0)
   {
      rp.reason = "invalid_add_risk_per_lot";
      return false;
   }

   rp.rawLots = desiredRiskMoney / rp.riskPerLot;
   if(rp.rawLots < minLot)
   {
      rp.actualRiskMoney = rp.riskPerLot * minLot;
      rp.actualRiskPct = (equity > 0.0) ? rp.actualRiskMoney / equity * 100.0 : 0.0;
      rp.reason = "raw_lot_below_min_lot";
      return false;
   }

   rp.lots = MathFloor(rp.rawLots / step) * step;
   rp.lots = MathMin(maxLot, rp.lots);
   rp.lots = NormalizeDouble(rp.lots, 2);
   if(rp.lots < minLot)
   {
      rp.reason = "normalized_lot_below_min_lot";
      return false;
   }

   rp.actualRiskMoney = rp.riskPerLot * rp.lots;
   rp.actualRiskPct = (equity > 0.0) ? rp.actualRiskMoney / equity * 100.0 : 0.0;
   if(rp.actualRiskMoney > desiredRiskMoney + 0.01)
   {
      rp.reason = "actual_add_risk_exceeds_desired";
      return false;
   }

   return true;
}

double TP1RFor(long positionType)
{
   if(!UseDirectionalExitProfile)
      return TP1_R;
   return (positionType == POSITION_TYPE_BUY) ? LongTP1_R : ShortTP1_R;
}

double BreakEvenTriggerFor(long positionType)
{
   if(!UseDirectionalExitProfile)
      return BreakEvenTriggerR;
   return (positionType == POSITION_TYPE_BUY) ? LongBreakEvenTriggerR : ShortBreakEvenTriggerR;
}

double StartTrailingAfterFor(long positionType)
{
   if(!UseDirectionalExitProfile)
      return StartTrailingAfterR;
   return (positionType == POSITION_TYPE_BUY) ? LongStartTrailingAfterR : ShortStartTrailingAfterR;
}

double TrailATRMultiplierFor(long positionType)
{
   if(!UseDirectionalExitProfile)
      return TrailATRMultiplier;
   return (positionType == POSITION_TYPE_BUY) ? LongTrailATRMultiplier : ShortTrailATRMultiplier;
}

double TP2RSILevelFor(long positionType)
{
   if(!UseDirectionalExitProfile)
      return (positionType == POSITION_TYPE_BUY) ? 65.0 : 35.0;
   return (positionType == POSITION_TYPE_BUY) ? LongTP2RSILevel : ShortTP2RSILevel;
}

double H4ExitRSILevelFor(long positionType)
{
   if(!UseDirectionalExitProfile)
      return (positionType == POSITION_TYPE_BUY) ? Overbought : Oversold;
   return (positionType == POSITION_TYPE_BUY) ? LongH4ExitRSILevel : ShortH4ExitRSILevel;
}

void TrackTP1Exit(long positionType)
{
   if(positionType == POSITION_TYPE_BUY)
      diagLongTP1++;
   else
      diagShortTP1++;
}

void TrackTP2Exit(long positionType)
{
   if(positionType == POSITION_TYPE_BUY)
      diagLongTP2++;
   else
      diagShortTP2++;
}

void TrackH4Exit(long positionType)
{
   if(positionType == POSITION_TYPE_BUY)
      diagLongH4Exit++;
   else
      diagShortH4Exit++;
}

void TrackTrailUpdate(long positionType)
{
   diagTrailExit++;
   if(positionType == POSITION_TYPE_BUY)
      diagLongTrailUpdates++;
   else
      diagShortTrailUpdates++;
}

bool ShortInvalidationAllowsExit(long positionType, bool tp1Completed, double rMultiple, const TFState &entryState)
{
   if(!UseShortInvalidationExit || positionType != POSITION_TYPE_SELL || tp1Completed)
      return false;
   if(rMultiple > ShortInvalidationMaxR)
      return false;
   return (entryState.crossRSIUpEMA && entryState.rsi1 > ShortInvalidationRSILevel);
}

void ManageHedgingPyramidGroup()
{
   if(CountManagedPositions() <= 0)
   {
      managedTicket = 0;
      tp1Done = false;
      tp2Done = false;
      initialPositionVolume = 0.0;
      managedInitialRiskDistance = 0.0;
      ResetPyramidCycle();
      return;
   }

   if(!pyramidCycleActive && !RecoverHedgingPyramidGroup())
      return;

   if(!SyncHedgingPyramidLegs())
   {
      ResetPyramidCycle();
      return;
   }

   int baseIndex = FirstOpenPyramidLegIndex();
   if(baseIndex < 0)
   {
      ResetPyramidCycle();
      return;
   }

   ulong activeTicket = pyramidLegs[baseIndex].ticket;
   if(activeTicket == 0 || !PositionSelectByTicket(activeTicket))
      return;

   managedTicket = activeTicket;
   long positionType = PositionGetInteger(POSITION_TYPE);
   double currentSL = 0.0;
   double tp = 0.0;
   if(!GetPyramidCurrentStopAndTP(positionType, currentSL, tp))
      return;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double current = (positionType == POSITION_TYPE_BUY) ? bid : ask;
   bool pyramidHasAdds = (pyramidAddCount > 0);
   double referenceEntry = pyramidBaseEntry;
   double initialRisk = pyramidInitialRiskDistance;
   if(initialRisk <= _Point)
      initialRisk = MathAbs(referenceEntry - currentSL);
   if(initialRisk <= _Point)
      return;

   double profitDistance = (positionType == POSITION_TYPE_BUY) ? current - referenceEntry : referenceEntry - current;
   double rMultiple = profitDistance / initialRisk;

   if(rMultiple >= BreakEvenTriggerFor(positionType))
   {
      MoveSLToBreakEven(positionType, referenceEntry, currentSL, tp);
      GetPyramidCurrentStopAndTP(positionType, currentSL, tp);
   }

   if(UsePartialExits && !pyramidHasAdds && !tp1Done && rMultiple >= TP1RFor(positionType))
   {
      double activeVolume = PositionGetDouble(POSITION_VOLUME);
      if(ClosePartialByTicket(activeTicket, activeVolume, TP1ClosePct, "TP1"))
      {
         tp1Done = true;
         TrackTP1Exit(positionType);
         if(GetPyramidCurrentStopAndTP(positionType, currentSL, tp))
            MoveSLToBreakEven(positionType, referenceEntry, currentSL, tp);
      }
   }

   TFState entryState, h1, h4;
   if(!BuildState(EntryTF, entryState) || !BuildState(PERIOD_H1, h1) || !BuildState(PERIOD_H4, h4))
      return;

   if(ShortInvalidationAllowsExit(positionType, tp1Done, rMultiple, entryState))
   {
      if(ClosePyramidGroup())
         diagShortInvalidationExit++;
      return;
   }

   if(TrailMode != TRAIL_OFF && rMultiple >= StartTrailingAfterFor(positionType))
   {
      if(GetPyramidCurrentStopAndTP(positionType, currentSL, tp))
         ApplyTrailingStop(positionType, currentSL, tp, entryState);
   }

   double tp2Level = TP2RSILevelFor(positionType);
   bool entryExitLong = (entryState.rsi2 >= tp2Level && entryState.rsi1 < entryState.rsi2 && entryState.crossRSIDownEMA);
   bool h1ExitLong = (h1.rsi2 >= tp2Level && h1.rsi1 < h1.rsi2 && h1.crossRSIDownEMA);
   bool entryExitShort = (entryState.rsi2 <= tp2Level && entryState.rsi1 > entryState.rsi2 && entryState.crossRSIUpEMA);
   bool h1ExitShort = (h1.rsi2 <= tp2Level && h1.rsi1 > h1.rsi2 && h1.crossRSIUpEMA);

   if(UsePartialExits && !pyramidHasAdds && tp1Done && !tp2Done)
   {
      bool tp2Signal = (positionType == POSITION_TYPE_BUY) ? (entryExitLong || h1ExitLong) : (entryExitShort || h1ExitShort);
      if(tp2Signal && PositionSelectByTicket(activeTicket) &&
         ClosePartialByTicket(activeTicket, PositionGetDouble(POSITION_VOLUME), TP2ClosePct, "TP2_RSI"))
      {
         tp2Done = true;
         TrackTP2Exit(positionType);
      }
   }

   bool h4Exit = false;
   double h4ExitLevel = H4ExitRSILevelFor(positionType);
   if(positionType == POSITION_TYPE_BUY)
      h4Exit = (h4.rsi2 > h4ExitLevel && h4.rsi1 < h4.rsi2 && h4.crossRSIDownEMA);
   else
      h4Exit = (h4.rsi2 < h4ExitLevel && h4.rsi1 > h4.rsi2 && h4.crossRSIUpEMA);

   if(h4Exit)
   {
      if(ClosePyramidGroup())
         TrackH4Exit(positionType);
      return;
   }

   if(pyramidCycleActive && !pyramidRecoveredPosition)
      TryPyramidAdd(positionType, entryState, h1, h4, rMultiple);
}

void ManageOpenPosition()
{
   if(IsHedgingPyramidMode())
   {
      ManageHedgingPyramidGroup();
      return;
   }

   if(!SelectManagedPosition())
   {
      managedTicket = 0;
      tp1Done = false;
      tp2Done = false;
      initialPositionVolume = 0.0;
      managedInitialRiskDistance = 0.0;
      ResetPyramidCycle();
      return;
   }

   ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
   if(managedTicket != ticket)
   {
      managedTicket = ticket;
      tp1Done = false;
      tp2Done = false;
      initialPositionVolume = PositionGetDouble(POSITION_VOLUME);
      managedInitialRiskDistance = MathAbs(PositionGetDouble(POSITION_PRICE_OPEN) - PositionGetDouble(POSITION_SL));
      if(UsePyramiding && !pyramidCycleActive)
      {
         pyramidRecoveredPosition = true;
         Print("PYRAMID recovered an existing position; additions are disabled until the next base trade.");
      }
   }

   long positionType = PositionGetInteger(POSITION_TYPE);
   double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   double volume = PositionGetDouble(POSITION_VOLUME);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double current = (positionType == POSITION_TYPE_BUY) ? bid : ask;
   bool pyramidHasAdds = (UsePyramiding && pyramidCycleActive && pyramidAddCount > 0);
   double referenceEntry = (UsePyramiding && pyramidCycleActive) ? pyramidBaseEntry : entryPrice;
   double initialRisk = (UsePyramiding && pyramidCycleActive) ? pyramidInitialRiskDistance : managedInitialRiskDistance;
   if(initialRisk <= _Point)
      initialRisk = MathAbs(referenceEntry - sl);

   if(initialRisk <= _Point)
      return;

   double profitDistance = (positionType == POSITION_TYPE_BUY) ? current - referenceEntry : referenceEntry - current;
   double rMultiple = profitDistance / initialRisk;

   if(rMultiple >= BreakEvenTriggerFor(positionType))
      MoveSLToBreakEven(positionType, referenceEntry, sl, tp);

   if(UsePartialExits && !pyramidHasAdds && !tp1Done && rMultiple >= TP1RFor(positionType))
   {
      if(ClosePartial(volume, TP1ClosePct, "TP1"))
      {
         tp1Done = true;
         TrackTP1Exit(positionType);
         MoveSLToBreakEven(positionType, referenceEntry, PositionGetDouble(POSITION_SL), PositionGetDouble(POSITION_TP));
      }
   }

   sl = PositionGetDouble(POSITION_SL);
   tp = PositionGetDouble(POSITION_TP);

   TFState entryState, h1, h4;
   if(!BuildState(EntryTF, entryState) || !BuildState(PERIOD_H1, h1) || !BuildState(PERIOD_H4, h4))
      return;

   if(ShortInvalidationAllowsExit(positionType, tp1Done, rMultiple, entryState))
   {
      if(trade.PositionClose(_Symbol))
         diagShortInvalidationExit++;
      return;
   }

   if(TrailMode != TRAIL_OFF && rMultiple >= StartTrailingAfterFor(positionType))
      ApplyTrailingStop(positionType, sl, tp, entryState);

   double tp2Level = TP2RSILevelFor(positionType);
   bool entryExitLong = (entryState.rsi2 >= tp2Level && entryState.rsi1 < entryState.rsi2 && entryState.crossRSIDownEMA);
   bool h1ExitLong = (h1.rsi2 >= tp2Level && h1.rsi1 < h1.rsi2 && h1.crossRSIDownEMA);
   bool entryExitShort = (entryState.rsi2 <= tp2Level && entryState.rsi1 > entryState.rsi2 && entryState.crossRSIUpEMA);
   bool h1ExitShort = (h1.rsi2 <= tp2Level && h1.rsi1 > h1.rsi2 && h1.crossRSIUpEMA);

   if(UsePartialExits && !pyramidHasAdds && tp1Done && !tp2Done)
   {
      bool tp2Signal = (positionType == POSITION_TYPE_BUY) ? (entryExitLong || h1ExitLong) : (entryExitShort || h1ExitShort);
      if(tp2Signal && ClosePartial(PositionGetDouble(POSITION_VOLUME), TP2ClosePct, "TP2_RSI"))
      {
         tp2Done = true;
         TrackTP2Exit(positionType);
      }
   }

   bool h4Exit = false;
   double h4ExitLevel = H4ExitRSILevelFor(positionType);
   if(positionType == POSITION_TYPE_BUY)
   {
      h4Exit = (h4.rsi2 > h4ExitLevel && h4.rsi1 < h4.rsi2 && h4.crossRSIDownEMA);
   }
   else
   {
      h4Exit = (h4.rsi2 < h4ExitLevel && h4.rsi1 > h4.rsi2 && h4.crossRSIUpEMA);
   }

   if(h4Exit)
   {
      if(trade.PositionClose(_Symbol))
         TrackH4Exit(positionType);
      return;
   }

   if(UsePyramiding && pyramidCycleActive && !pyramidRecoveredPosition)
      TryPyramidAdd(positionType, entryState, h1, h4, rMultiple);
}

void UpdatePyramidPeakEquity()
{
   if(!UsePyramiding)
      return;

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity > pyramidPeakEquity)
      pyramidPeakEquity = equity;
}

double PyramidEquityDrawdownPct()
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(pyramidPeakEquity <= 0.0 || equity >= pyramidPeakEquity)
      return 0.0;
   return (pyramidPeakEquity - equity) / pyramidPeakEquity * 100.0;
}

void ResetPyramidCycle()
{
   ArrayResize(pyramidLegs, 0);
   pyramidCycleActive = false;
   pyramidRecoveredPosition = false;
   pyramidAddCount = 0;
   pyramidLastAddBarTime = 0;
   pyramidBaseEntry = 0.0;
   pyramidInitialRiskDistance = 0.0;
   pyramidBaseRiskMoney = 0.0;
   pyramidRealizedNetProfit = 0.0;
}

double RiskMoneyForDistance(double volume, double riskDistance)
{
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(volume <= 0.0 || riskDistance <= 0.0 || tickValue <= 0.0 || tickSize <= 0.0)
      return 0.0;
   return riskDistance / tickSize * tickValue * volume;
}

void StartPyramidCycle(ENUM_ORDER_TYPE type, double entryPrice, double volume, double initialSL, ulong ticket)
{
   ResetPyramidCycle();

   double riskDistance = MathAbs(entryPrice - initialSL);
   double riskMoney = RiskMoneyForDistance(volume, riskDistance);
   if(riskDistance <= _Point || riskMoney <= 0.0)
   {
      Print("PYRAMID cycle not initialized: invalid base risk.");
      return;
   }

   ArrayResize(pyramidLegs, 1);
   pyramidLegs[0].ticket = ticket;
   pyramidLegs[0].identifier = PositionIdentifierByTicket(ticket);
   pyramidLegs[0].entryPrice = entryPrice;
   pyramidLegs[0].volume = volume;
   pyramidLegs[0].type = type;
   pyramidCycleActive = true;
   pyramidBaseEntry = entryPrice;
   pyramidInitialRiskDistance = riskDistance;
   pyramidBaseRiskMoney = riskMoney;
   diagPyramidCycles++;

   Print("PYRAMID base cycle entry=", DoubleToString(entryPrice, _Digits),
         " lots=", DoubleToString(volume, 2),
         " initialRiskMoney=", DoubleToString(riskMoney, 2));
}

void AppendPyramidLeg(ENUM_ORDER_TYPE type, double entryPrice, double volume, ulong ticket)
{
   int size = ArraySize(pyramidLegs);
   ArrayResize(pyramidLegs, size + 1);
   pyramidLegs[size].ticket = ticket;
   pyramidLegs[size].identifier = PositionIdentifierByTicket(ticket);
   pyramidLegs[size].entryPrice = entryPrice;
   pyramidLegs[size].volume = volume;
   pyramidLegs[size].type = type;
}

void ReducePyramidLegs(double closedVolume)
{
   double remaining = closedVolume;
   for(int i = 0; i < ArraySize(pyramidLegs) && remaining > 0.0; i++)
   {
      double reduction = MathMin(pyramidLegs[i].volume, remaining);
      pyramidLegs[i].volume -= reduction;
      remaining -= reduction;
   }
}

void ReducePyramidLegsByIdentifier(long identifier, double closedVolume)
{
   if(identifier <= 0)
   {
      ReducePyramidLegs(closedVolume);
      return;
   }

   double remaining = closedVolume;
   for(int i = 0; i < ArraySize(pyramidLegs) && remaining > 0.0; i++)
   {
      if(pyramidLegs[i].identifier != identifier)
         continue;
      double reduction = MathMin(pyramidLegs[i].volume, remaining);
      pyramidLegs[i].volume -= reduction;
      remaining -= reduction;
   }

   if(remaining > 0.0)
      ReducePyramidLegs(remaining);
}

int FirstOpenPyramidLegIndex()
{
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   for(int i = 0; i < ArraySize(pyramidLegs); i++)
   {
      if(pyramidLegs[i].volume >= minLot * 0.5)
         return i;
   }
   return -1;
}

double TotalPyramidOpenVolume()
{
   double total = 0.0;
   for(int i = 0; i < ArraySize(pyramidLegs); i++)
      total += MathMax(0.0, pyramidLegs[i].volume);
   return total;
}

bool SyncHedgingPyramidLegs()
{
   if(!IsHedgingPyramidMode())
      return true;

   bool anyOpen = false;
   for(int i = 0; i < ArraySize(pyramidLegs); i++)
   {
      ulong ticket = pyramidLegs[i].ticket;
      if(ticket > 0 && PositionSelectByTicket(ticket) && SelectedPositionIsManaged())
      {
         pyramidLegs[i].entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         pyramidLegs[i].volume = PositionGetDouble(POSITION_VOLUME);
         pyramidLegs[i].identifier = (long)PositionGetInteger(POSITION_IDENTIFIER);
         anyOpen = true;
      }
      else
      {
         pyramidLegs[i].volume = 0.0;
      }
   }
   return anyOpen;
}

ENUM_ORDER_TYPE PositionTypeToOrderType(long positionType)
{
   return (positionType == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
}

bool RecoverHedgingPyramidGroup()
{
   if(!IsHedgingPyramidMode() || CountManagedPositions() <= 0)
      return false;

   ulong baseTicket = 0;
   long oldestTime = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(!SelectedPositionIsManaged())
         continue;

      long timeMsc = (long)PositionGetInteger(POSITION_TIME_MSC);
      if(baseTicket == 0 || timeMsc < oldestTime)
      {
         oldestTime = timeMsc;
         baseTicket = ticket;
      }
   }

   if(baseTicket == 0 || !PositionSelectByTicket(baseTicket))
      return false;

   long basePositionType = PositionGetInteger(POSITION_TYPE);
   ENUM_ORDER_TYPE baseOrderType = PositionTypeToOrderType(basePositionType);
   double baseEntry = PositionGetDouble(POSITION_PRICE_OPEN);
   double baseVolume = PositionGetDouble(POSITION_VOLUME);
   double baseSL = PositionGetDouble(POSITION_SL);
   StartPyramidCycle(baseOrderType, baseEntry, baseVolume, baseSL, baseTicket);
   if(!pyramidCycleActive)
      return false;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || ticket == baseTicket || !PositionSelectByTicket(ticket))
         continue;
      if(!SelectedPositionIsManaged())
         continue;
      if(PositionGetInteger(POSITION_TYPE) != basePositionType)
         continue;

      AppendPyramidLeg(baseOrderType, PositionGetDouble(POSITION_PRICE_OPEN),
                       PositionGetDouble(POSITION_VOLUME), ticket);
   }

   pyramidAddCount = ArraySize(pyramidLegs) - 1;
   if(pyramidAddCount < 0)
      pyramidAddCount = 0;
   if(pyramidAddCount > MaxPyramidAdds)
      pyramidAddCount = MaxPyramidAdds;
   pyramidRecoveredPosition = true;
   Print("PYRAMID recovered hedging group; additions are disabled until the next base trade. legs=",
         ArraySize(pyramidLegs));
   return true;
}

double StopModifyStep()
{
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize <= 0.0)
      tickSize = _Point;
   return MathMax(_Point, tickSize);
}

bool StopImproves(long positionType, double targetSL, double currentSL)
{
   targetSL = NormalizeDouble(targetSL, _Digits);
   currentSL = NormalizeDouble(currentSL, _Digits);
   if(currentSL <= 0.0)
      return true;

   double step = StopModifyStep();
   if(positionType == POSITION_TYPE_BUY)
      return (targetSL - currentSL >= step);
   return (currentSL - targetSL >= step);
}

bool GetPyramidCurrentStopAndTP(long positionType, double &currentSL, double &tp)
{
   currentSL = 0.0;
   tp = 0.0;

   if(!IsHedgingPyramidMode())
   {
      if(!SelectManagedPosition())
         return false;
      currentSL = PositionGetDouble(POSITION_SL);
      tp = PositionGetDouble(POSITION_TP);
      return true;
   }

   if(!SyncHedgingPyramidLegs())
      return false;

   bool found = false;
   for(int i = 0; i < ArraySize(pyramidLegs); i++)
   {
      if(pyramidLegs[i].volume <= 0.0 || pyramidLegs[i].ticket == 0 ||
         !PositionSelectByTicket(pyramidLegs[i].ticket))
         continue;

      double sl = PositionGetDouble(POSITION_SL);
      if(sl <= 0.0)
         return false;
      if(!found)
      {
         currentSL = sl;
         tp = PositionGetDouble(POSITION_TP);
         found = true;
      }
      else if(positionType == POSITION_TYPE_BUY)
         currentSL = MathMin(currentSL, sl);
      else
         currentSL = MathMax(currentSL, sl);
   }

   return found;
}

bool ModifyPyramidStop(long positionType, double targetSL, double tp)
{
   targetSL = NormalizeDouble(targetSL, _Digits);
   if(!IsPyramidStopValid(positionType, targetSL))
      return false;

   if(!IsHedgingPyramidMode())
   {
      if(!SelectManagedPosition())
         return false;

      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      if(!StopImproves(positionType, targetSL, currentSL))
         return false;
      return trade.PositionModify(_Symbol, targetSL, currentTP);
   }

   bool ok = true;
   bool touched = false;
   for(int i = 0; i < ArraySize(pyramidLegs); i++)
   {
      if(pyramidLegs[i].volume <= 0.0 || pyramidLegs[i].ticket == 0 ||
         !PositionSelectByTicket(pyramidLegs[i].ticket))
         continue;

      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      if(!StopImproves(positionType, targetSL, currentSL))
         continue;

      touched = true;
      if(!trade.PositionModify(pyramidLegs[i].ticket, targetSL, currentTP))
         ok = false;
   }

   return ok && touched;
}

bool ClosePyramidGroup()
{
   if(!IsHedgingPyramidMode())
      return trade.PositionClose(_Symbol);

   bool ok = true;
   bool touched = false;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(!SelectedPositionIsManaged())
         continue;

      touched = true;
      if(!trade.PositionClose(ticket))
         ok = false;
   }
   return ok && touched;
}

double PyramidLegProfitAtStop(const PyramidLeg &leg, double stopPrice)
{
   if(leg.volume <= 0.0)
      return 0.0;

   double profit = 0.0;
   if(!OrderCalcProfit(leg.type, _Symbol, leg.volume, leg.entryPrice, stopPrice, profit))
      return -1.0e100;
   return profit;
}

double PyramidBundleStopPnL(double stopPrice)
{
   double pnl = pyramidRealizedNetProfit;
   for(int i = 0; i < ArraySize(pyramidLegs); i++)
   {
      double legPnl = PyramidLegProfitAtStop(pyramidLegs[i], stopPrice);
      if(legPnl <= -1.0e99)
         return -1.0e100;
      pnl += legPnl;
   }
   return pnl;
}

bool PyramidSignal(long positionType, const TFState &entry, const TFState &h1, const TFState &h4)
{
   TFState d1;
   if(!BuildState(PERIOD_D1, d1))
      return false;

   int bullCount = 0;
   int bearCount = 0;
   CountBias(d1, bullCount, bearCount);
   CountBias(h4, bullCount, bearCount);
   CountBias(h1, bullCount, bearCount);

   if(entry.chop)
      return false;

   if(positionType == POSITION_TYPE_BUY)
   {
      return (BiasAllowsLong(d1, h4, h1, bullCount) &&
              entry.rsi1 > entry.ema1 && entry.rsi1 > entry.rsi2 && entry.ema1 >= entry.ema2 &&
              entry.rsi1 <= PyramidLongRSIMax);
   }

   return (BiasAllowsShort(d1, h4, h1, bearCount) &&
           entry.rsi1 < entry.ema1 && entry.rsi1 < entry.rsi2 && entry.ema1 <= entry.ema2 &&
           entry.rsi1 >= PyramidShortRSIMin);
}

bool PyramidSpacingAllowsAdd()
{
   if(pyramidLastAddBarTime == 0 || PyramidMinBarsBetweenAdds <= 0)
      return true;

   int barsSinceAdd = iBarShift(_Symbol, EntryTF, pyramidLastAddBarTime, false);
   return (barsSinceAdd >= PyramidMinBarsBetweenAdds);
}

bool IsPyramidStopValid(long positionType, double stopPrice)
{
   stopPrice = NormalizeDouble(stopPrice, _Digits);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double stopsLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double freezeLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL) * _Point;
   double minDistance = MathMax(stopsLevel, freezeLevel) + StopModifyStep();

   if(positionType == POSITION_TYPE_BUY)
      return (stopPrice < bid - minDistance);
   return (stopPrice > ask + minDistance);
}

bool EnsurePyramidStop(long positionType, double targetSL, double currentSL, double tp)
{
   targetSL = NormalizeDouble(targetSL, _Digits);
   currentSL = NormalizeDouble(currentSL, _Digits);

   if(!StopImproves(positionType, targetSL, currentSL))
      return true;

   if(!IsPyramidStopValid(positionType, targetSL))
   {
      diagPyramidStopModifySkip++;
      return false;
   }

   if(!ModifyPyramidStop(positionType, targetSL, tp))
   {
      diagPyramidStopModifyFail++;
      Print("PYRAMID skip add: common stop modification failed retcode=", trade.ResultRetcode(),
            " ", trade.ResultRetcodeDescription(),
            " currentSL=", DoubleToString(currentSL, _Digits),
            " targetSL=", DoubleToString(targetSL, _Digits));
      return false;
   }
   return true;
}

bool HasPyramidMargin(ENUM_ORDER_TYPE type, double volume, double price)
{
   double marginRequired = 0.0;
   if(!OrderCalcMargin(type, _Symbol, volume, price, marginRequired))
      return false;

   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double marginLevel = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   if(freeMargin <= marginRequired)
      return false;
   if(marginLevel > 0.0 && marginLevel < PyramidMinMarginLevelPct)
      return false;
   return true;
}

void TrackPyramidWorstStopPnL(double stopPnl)
{
   if(pyramidBaseRiskMoney <= 0.0)
      return;

   double stopPnLR = stopPnl / pyramidBaseRiskMoney;
   if(diagPyramidWorstBundleStopPnLR == 0.0 || stopPnLR < diagPyramidWorstBundleStopPnLR)
      diagPyramidWorstBundleStopPnLR = stopPnLR;
}

void TryPyramidAdd(long positionType, const TFState &entry, const TFState &h1, const TFState &h4, double baseRMultiple)
{
   if(pyramidAddCount >= MaxPyramidAdds || pyramidBaseRiskMoney <= 0.0 ||
      (PyramidDisableAtEquityDDPct > 0.0 && PyramidEquityDrawdownPct() >= PyramidDisableAtEquityDDPct) ||
      !PyramidSpacingAllowsAdd())
      return;

   int stage = 0;
   double triggerR = 0.0;
   double addRiskR = 0.0;
   double lockFloorR = 0.0;
   if(pyramidAddCount == 0 && baseRMultiple >= Add1TriggerR)
   {
      stage = 1;
      triggerR = Add1TriggerR;
      addRiskR = Add1RiskR;
      lockFloorR = Add1LockFloorR;
   }
   else if(pyramidAddCount == 1 && MaxPyramidAdds >= 2 && baseRMultiple >= Add2TriggerR)
   {
      stage = 2;
      triggerR = Add2TriggerR;
      addRiskR = Add2RiskR;
      lockFloorR = Add2LockFloorR;
   }
   else
      return;

   if(!PyramidSignal(positionType, entry, h1, h4))
      return;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double spreadR = (ask - bid) / pyramidInitialRiskDistance;
   if(spreadR > PyramidMaxSpreadR)
   {
      diagPyramidSkipSpread++;
      return;
   }

   double currentSL = 0.0;
   double tp = 0.0;
   if(!GetPyramidCurrentStopAndTP(positionType, currentSL, tp))
      return;
   double floorSL = (positionType == POSITION_TYPE_BUY) ?
                    pyramidBaseEntry + lockFloorR * pyramidInitialRiskDistance :
                    pyramidBaseEntry - lockFloorR * pyramidInitialRiskDistance;
   double sharedSL = (positionType == POSITION_TYPE_BUY) ? MathMax(currentSL, floorSL) :
                     ((currentSL > 0.0) ? MathMin(currentSL, floorSL) : floorSL);

   if(!EnsurePyramidStop(positionType, sharedSL, currentSL, tp) ||
      !GetPyramidCurrentStopAndTP(positionType, currentSL, tp))
      return;
   sharedSL = currentSL;

   double existingStopPnl = PyramidBundleStopPnL(sharedSL);
   if(existingStopPnl <= -1.0e99)
      return;

   double reserveMoney = PyramidCostReserveR * pyramidBaseRiskMoney;
   double minLockedMoney = PyramidMinLockedProfitR * pyramidBaseRiskMoney;
   double desiredAddRiskMoney = addRiskR * pyramidBaseRiskMoney;
   if(existingStopPnl - desiredAddRiskMoney - reserveMoney < minLockedMoney)
   {
      diagPyramidSkipLockedPnl++;
      TrackPyramidWorstStopPnL(existingStopPnl - reserveMoney);
      return;
   }

   ENUM_ORDER_TYPE orderType = (positionType == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double entryPrice = (positionType == POSITION_TYPE_BUY) ? ask : bid;
   double riskDistance = MathAbs(entryPrice - sharedSL);
   if(riskDistance <= _Point)
      return;

   RiskPlan rp;
   if(!BuildRiskPlanForMoney(riskDistance, desiredAddRiskMoney, rp))
   {
      if(rp.reason == "raw_lot_below_min_lot" || rp.reason == "normalized_lot_below_min_lot")
         diagPyramidSkipMinLot++;
      return;
   }

   PyramidLeg candidate;
   candidate.ticket = 0;
   candidate.identifier = 0;
   candidate.entryPrice = entryPrice;
   candidate.volume = rp.lots;
   candidate.type = orderType;
   double projectedStopPnl = existingStopPnl + PyramidLegProfitAtStop(candidate, sharedSL) - reserveMoney;
   if(projectedStopPnl < minLockedMoney)
   {
      diagPyramidSkipLockedPnl++;
      TrackPyramidWorstStopPnL(projectedStopPnl);
      return;
   }

   if(!HasPyramidMargin(orderType, rp.lots, entryPrice))
   {
      diagPyramidSkipMargin++;
      return;
   }

   string comment = (stage == 1) ? "RSI_MTF_PYR1" : "RSI_MTF_PYR2";
   bool opened = (orderType == ORDER_TYPE_BUY) ?
                 trade.Buy(rp.lots, _Symbol, entryPrice, sharedSL, 0.0, comment) :
                 trade.Sell(rp.lots, _Symbol, entryPrice, sharedSL, 0.0, comment);
   if(!opened)
   {
      Print("PYRAMID add", stage, " failed: ", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
      return;
   }

   double fillPrice = trade.ResultPrice();
   if(fillPrice <= 0.0)
      fillPrice = entryPrice;
   ulong addTicket = 0;
   if(IsHedgingPyramidMode())
   {
      long openedPositionType = (orderType == ORDER_TYPE_BUY) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
      addTicket = FindNewestManagedPositionTicket(comment, openedPositionType, rp.lots);
      if(addTicket > 0 && PositionSelectByTicket(addTicket))
         fillPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      else
      {
         diagPyramidPostFillViolation++;
         Print("PYRAMID add", stage, " ticket could not be identified on hedging account; closing the full group.");
         ClosePyramidGroup();
         return;
      }
   }
   AppendPyramidLeg(orderType, fillPrice, rp.lots, addTicket);
   pyramidAddCount = stage;
   pyramidLastAddBarTime = iTime(_Symbol, EntryTF, 0);
   tp1Done = true;
   tp2Done = true;
   if(stage == 1)
      diagPyramidAdd1Opened++;
   else
      diagPyramidAdd2Opened++;

   double postFillStopPnl = PyramidBundleStopPnL(sharedSL) - reserveMoney;
   TrackPyramidWorstStopPnL(postFillStopPnl);
   if(postFillStopPnl < minLockedMoney)
   {
      diagPyramidPostFillViolation++;
      Print("PYRAMID post-fill risk violation; closing the full group. stopPnL=", DoubleToString(postFillStopPnl, 2));
      ClosePyramidGroup();
      return;
   }

   Print("PYRAMID add", stage,
         " triggerR=", DoubleToString(triggerR, 2),
         " lots=", DoubleToString(rp.lots, 2),
         " sharedSL=", DoubleToString(sharedSL, _Digits),
         " lockedStopPnL=", DoubleToString(postFillStopPnl, 2));
}

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(!UsePyramiding || !pyramidCycleActive || trans.type != TRADE_TRANSACTION_DEAL_ADD || trans.deal == 0)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol ||
      (int)HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != MagicNumber)
      return;

   long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY)
      return;

   double net = HistoryDealGetDouble(trans.deal, DEAL_PROFIT) +
                HistoryDealGetDouble(trans.deal, DEAL_COMMISSION) +
                HistoryDealGetDouble(trans.deal, DEAL_SWAP) +
                HistoryDealGetDouble(trans.deal, DEAL_FEE);
   pyramidRealizedNetProfit += net;
   if(IsHedgingPyramidMode())
      ReducePyramidLegsByIdentifier((long)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID),
                                    HistoryDealGetDouble(trans.deal, DEAL_VOLUME));
   else
      ReducePyramidLegs(HistoryDealGetDouble(trans.deal, DEAL_VOLUME));
}

void MoveSLToBreakEven(long positionType, double entryPrice, double currentSL, double tp)
{
   double beSL = (positionType == POSITION_TYPE_BUY) ? entryPrice + 2 * _Point : entryPrice - 2 * _Point;
   beSL = NormalizeDouble(beSL, _Digits);
   if(StopImproves(positionType, beSL, currentSL))
   {
      if(IsHedgingPyramidMode() && pyramidCycleActive)
         ModifyPyramidStop(positionType, beSL, tp);
      else
         trade.PositionModify(_Symbol, NormalizeDouble(beSL, _Digits), tp);
   }
}

void ApplyTrailingStop(long positionType, double currentSL, double tp, const TFState &entryState)
{
   double trailSL = 0.0;

   if(TrailMode == ATR_CHANDELIER)
      trailSL = ChandelierTrailSL(positionType, entryState.atr1, TrailATRMultiplierFor(positionType));

   if(trailSL <= 0.0)
      return;

   trailSL = NormalizeDouble(trailSL, _Digits);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(positionType == POSITION_TYPE_BUY && trailSL >= bid)
      return;
   if(positionType == POSITION_TYPE_SELL && trailSL <= ask)
      return;

   bool modified = false;
   if(StopImproves(positionType, trailSL, currentSL))
   {
      if(IsHedgingPyramidMode() && pyramidCycleActive)
         modified = ModifyPyramidStop(positionType, trailSL, tp);
      else
         modified = trade.PositionModify(_Symbol, trailSL, tp);
   }

   if(modified)
   {
      TrackTrailUpdate(positionType);
      Print("TRAIL update mode=", TrailModeText(), " sl=", DoubleToString(trailSL, _Digits));
   }
}

double ChandelierTrailSL(long positionType, double atr, double atrMultiplier)
{
   if(atr <= 0.0 || TrailLookbackBars < 2)
      return 0.0;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, EntryTF, 0, TrailLookbackBars + 2, rates) < TrailLookbackBars + 2)
      return 0.0;

   if(positionType == POSITION_TYPE_BUY)
   {
      double highest = rates[1].high;
      for(int i = 2; i <= TrailLookbackBars; i++)
         highest = MathMax(highest, rates[i].high);
      return highest - atr * atrMultiplier;
   }

   double lowest = rates[1].low;
   for(int i = 2; i <= TrailLookbackBars; i++)
      lowest = MathMin(lowest, rates[i].low);
   return lowest + atr * atrMultiplier;
}

bool ClosePartial(double currentVolume, double pct, string label)
{
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double closeLots = currentVolume * pct / 100.0;
   closeLots = MathFloor(closeLots / step) * step;
   closeLots = NormalizeDouble(closeLots, 2);

   if(initialPositionVolume > 0.0 && RunnerMinPct > 0.0 && RunnerMinPct < 100.0)
   {
      double runnerLots = initialPositionVolume * RunnerMinPct / 100.0;
      runnerLots = MathCeil(runnerLots / step) * step;
      runnerLots = NormalizeDouble(runnerLots, 2);

      if(currentVolume - closeLots < runnerLots)
         closeLots = currentVolume - runnerLots;
      closeLots = MathFloor(closeLots / step) * step;
      closeLots = NormalizeDouble(closeLots, 2);
   }

   if(closeLots < minLot)
      return false;
   if(currentVolume - closeLots < minLot)
      closeLots = currentVolume;

   bool ok = trade.PositionClosePartial(_Symbol, closeLots);
   if(ok)
      Print(label, " partial close lots=", DoubleToString(closeLots, 2));
   return ok;
}

bool ClosePartialByTicket(ulong ticket, double currentVolume, double pct, string label)
{
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double closeLots = currentVolume * pct / 100.0;
   closeLots = MathFloor(closeLots / step) * step;
   closeLots = NormalizeDouble(closeLots, 2);

   if(initialPositionVolume > 0.0 && RunnerMinPct > 0.0 && RunnerMinPct < 100.0)
   {
      double runnerLots = initialPositionVolume * RunnerMinPct / 100.0;
      runnerLots = MathCeil(runnerLots / step) * step;
      runnerLots = NormalizeDouble(runnerLots, 2);

      if(currentVolume - closeLots < runnerLots)
         closeLots = currentVolume - runnerLots;
      closeLots = MathFloor(closeLots / step) * step;
      closeLots = NormalizeDouble(closeLots, 2);
   }

   if(closeLots < minLot)
      return false;
   if(currentVolume - closeLots < minLot)
      closeLots = currentVolume;

   bool ok = trade.PositionClosePartial(ticket, closeLots);
   if(ok)
      Print(label, " partial close ticket=", ticket, " lots=", DoubleToString(closeLots, 2));
   return ok;
}

string BiasText(BiasState bias)
{
   if(bias == BIAS_BULL)
      return "bull";
   if(bias == BIAS_BEAR)
      return "bear";
   return "neutral";
}

string BiasModeText()
{
   if(BiasMode == STRICT_COUNT)
      return "STRICT_COUNT";
   return "HTF_VETO";
}

string RegimeGateModeText()
{
   if(RegimeGateMode == REGIME_D1_EARLY_VETO)
      return "D1_EARLY_VETO";
   if(RegimeGateMode == REGIME_D1_H4_COMPOSITE_VETO)
      return "D1_H4_COMPOSITE_VETO";
   return "OFF";
}

string TrailModeText()
{
   if(TrailMode == ATR_CHANDELIER)
      return "ATR_CHANDELIER";
   return "OFF";
}

string PyramidAccountModeText(PyramidAccountModeType mode)
{
   if(mode == PYRAMID_NETTING)
      return "PYRAMID_NETTING";
   if(mode == PYRAMID_HEDGING_GROUP)
      return "PYRAMID_HEDGING_GROUP";
   return "PYRAMID_AUTO";
}

string FanPointText(FanEntryPointType point)
{
   if(point == FAN_ENTRY1)
      return "E1";
   if(point == FAN_ENTRY2)
      return "E2";
   if(point == FAN_ENTRY3)
      return "E3";
   return "NONE";
}

string FanEntrySelectionText()
{
   if(FanEntrySelection == FAN_ENTRY1_ONLY)
      return "ENTRY1_ONLY";
   if(FanEntrySelection == FAN_ENTRY2_ONLY)
      return "ENTRY2_ONLY";
   if(FanEntrySelection == FAN_ENTRY3_ONLY)
      return "ENTRY3_ONLY";
   return "FIRST_VALID";
}

void TrackFanOpened(bool longSide, FanEntryPointType point)
{
   if(point == FAN_ENTRY1)
   {
      if(longSide)
         diagFanLongE1Opened++;
      else
         diagFanShortE1Opened++;
   }
   else if(point == FAN_ENTRY2)
   {
      if(longSide)
         diagFanLongE2Opened++;
      else
         diagFanShortE2Opened++;
   }
   else if(point == FAN_ENTRY3)
   {
      if(longSide)
         diagFanLongE3Opened++;
      else
         diagFanShortE3Opened++;
   }

}

string EntryModeText()
{
   if(EntryMode == RSI_CROSS_EMA)
      return "RSI_CROSS_EMA";
   if(EntryMode == RSI_PULLBACK_CONTINUATION)
      return "RSI_PULLBACK_CONTINUATION";
   if(EntryMode == RSI_FAN_STRUCTURE)
      return "RSI_FAN_STRUCTURE";
   return "RSI_ABOVE_EMA_AFTER_EXTREME";
}

string StateText(const TFState &s)
{
   return TFName(s.tf) + ":RSI=" + DoubleToString(s.rsi1, 2) +
          ",EMA=" + DoubleToString(s.ema1, 2) +
          ",WMA=" + DoubleToString(s.wma1, 2) +
          ",ATR=" + DoubleToString(s.atr1, _Digits) +
          ",bias=" + BiasText(s.bias);
}

string Snapshot(const TFState &d1, const TFState &h4, const TFState &h1, const TFState &m15)
{
   return StateText(d1) + " | " + StateText(h4) + " | " + StateText(h1) + " | " + StateText(m15);
}

void TrackReject(string reason)
{
   if(reason == "bias")
      diagRejectBias++;
   else if(reason == "chop")
      diagRejectChop++;
   else if(reason == "curl")
      diagRejectCurl++;
   else if(reason == "cross")
      diagRejectCross++;
   else if(reason == "ema_side")
      diagRejectEMASide++;
   else if(reason == "volume")
      diagRejectVolume++;
   else if(reason == "long_quality")
      diagRejectLongQuality++;
   else if(reason == "short_quality")
      diagRejectShortQuality++;
   else if(reason == "regime_long")
      diagRejectRegimeLong++;
   else if(reason == "regime_short")
      diagRejectRegimeShort++;
   else if(reason == "fan")
      diagRejectFan++;
}

void PrintDiagnostics(const TFState &d1, const TFState &h4, const TFState &h1, const TFState &m15, const TFState &entry, int bullCount, int bearCount)
{
   if(!Diagnostics)
      return;

   bool shouldPrint = (DiagnosticsEveryBars <= 1 || diagEntryBars % DiagnosticsEveryBars == 0);
   string entryModeText = EntryModeText();
   string biasModeText = BiasModeText();
   string snapshot = Snapshot(d1, h4, h1, m15);

   if(diagCsvHandle != INVALID_HANDLE)
   {
      FileWrite(diagCsvHandle, TimeToString(lastEntryBarTime), TFName(EntryTF), entryModeText, biasModeText,
                armedLongBars, armedShortBars, bullCount, bearCount, diagRejectBias,
                diagRejectChop, diagRejectRisk, diagRejectCurl,
                diagRejectCross, diagRejectEMASide, diagRejectVolume, diagRejectLongQuality, diagRejectShortQuality,
                RegimeGateModeText(), RegimeScore(d1), RegimeScore(h4), CompositeRegimeScore(d1, h4),
                diagRejectRegimeLong, diagRejectRegimeShort, pyramidAddCount,
                diagPyramidSkipLockedPnl, diagPyramidSkipMinLot, diagPyramidSkipSpread,
                diagPyramidSkipMargin, StateText(entry), snapshot);
   }

   if(!shouldPrint)
      return;

   Print("DIAG bar=", TimeToString(lastEntryBarTime),
         " entryTF=", TFName(EntryTF),
         " mode=", entryModeText,
         " biasMode=", biasModeText,
         " regimeGate=", RegimeGateModeText(),
         " regimeScore[D1=", RegimeScore(d1),
         ",H4=", RegimeScore(h4),
         ",composite=", CompositeRegimeScore(d1, h4),
         "]",
         " armedL=", armedLongBars,
         " armedS=", armedShortBars,
         " biasBull=", bullCount,
         " biasBear=", bearCount,
         " rejects[bias=", diagRejectBias,
         ",chop=", diagRejectChop,
         ",risk=", diagRejectRisk,
         ",curl=", diagRejectCurl,
         ",cross=", diagRejectCross,
         ",emaSide=", diagRejectEMASide,
         ",volume=", diagRejectVolume,
         ",longQuality=", diagRejectLongQuality,
         ",shortQuality=", diagRejectShortQuality,
         ",regimeL=", diagRejectRegimeLong,
         ",regimeS=", diagRejectRegimeShort,
         ",fan=", diagRejectFan,
         "] entry=", StateText(entry),
         " snapshot=", snapshot);
}

void PrintDiagnosticsSummary(string source)
{
   string usePyramidingText = UsePyramiding ? "true" : "false";

   string core = "DIAG_SUMMARY core source=" + source;
   core += " bars=" + IntegerToString(diagEntryBars);
   core += " trades=" + IntegerToString(diagTradesOpened);
   core += " longTrades=" + IntegerToString(diagLongOpened);
   core += " shortTrades=" + IntegerToString(diagShortOpened);
   core += " armedLong=" + IntegerToString(diagArmedLong);
   core += " armedShort=" + IntegerToString(diagArmedShort);
   Print(core);

   string rejects = "DIAG_SUMMARY rejects source=" + source;
   rejects += " bias=" + IntegerToString(diagRejectBias);
   rejects += " chop=" + IntegerToString(diagRejectChop);
   rejects += " risk=" + IntegerToString(diagRejectRisk);
   rejects += " curl=" + IntegerToString(diagRejectCurl);
   rejects += " cross=" + IntegerToString(diagRejectCross);
   rejects += " emaSide=" + IntegerToString(diagRejectEMASide);
   rejects += " volume=" + IntegerToString(diagRejectVolume);
   rejects += " longQuality=" + IntegerToString(diagRejectLongQuality);
   rejects += " shortQuality=" + IntegerToString(diagRejectShortQuality);
   rejects += " regimeL=" + IntegerToString(diagRejectRegimeLong);
   rejects += " regimeS=" + IntegerToString(diagRejectRegimeShort);
   rejects += " fan=" + IntegerToString(diagRejectFan);
   rejects += " trailUpdates=" + IntegerToString(diagTrailExit);
   Print(rejects);

   string regime = "DIAG_SUMMARY regime source=" + source;
   regime += " mode=" + RegimeGateModeText();
   regime += " blockedL=" + IntegerToString(diagRejectRegimeLong);
   regime += " blockedS=" + IntegerToString(diagRejectRegimeShort);
   Print(regime);

   string regimeLong = "DIAG_SUMMARY regimeLong source=" + source;
   regimeLong += " bull=" + IntegerToString(diagRegimeLongOpenBull);
   regimeLong += " neutral=" + IntegerToString(diagRegimeLongOpenNeutral);
   regimeLong += " bear=" + IntegerToString(diagRegimeLongOpenBear);
   Print(regimeLong);

   string regimeShort = "DIAG_SUMMARY regimeShort source=" + source;
   regimeShort += " bull=" + IntegerToString(diagRegimeShortOpenBull);
   regimeShort += " neutral=" + IntegerToString(diagRegimeShortOpenNeutral);
   regimeShort += " bear=" + IntegerToString(diagRegimeShortOpenBear);
   Print(regimeShort);

   string pyramid = "DIAG_SUMMARY pyramid source=" + source;
   pyramid += " cycles=" + IntegerToString(diagPyramidCycles);
   pyramid += " add1=" + IntegerToString(diagPyramidAdd1Opened);
   pyramid += " add2=" + IntegerToString(diagPyramidAdd2Opened);
   pyramid += " skipLocked=" + IntegerToString(diagPyramidSkipLockedPnl);
   pyramid += " skipMinLot=" + IntegerToString(diagPyramidSkipMinLot);
   pyramid += " skipSpread=" + IntegerToString(diagPyramidSkipSpread);
   pyramid += " skipMargin=" + IntegerToString(diagPyramidSkipMargin);
   pyramid += " stopModifyFail=" + IntegerToString(diagPyramidStopModifyFail);
   pyramid += " stopModifySkip=" + IntegerToString(diagPyramidStopModifySkip);
   pyramid += " postFillViolation=" + IntegerToString(diagPyramidPostFillViolation);
   pyramid += " worstStopPnLR=" + DoubleToString(diagPyramidWorstBundleStopPnLR, 2);
   Print(pyramid);

   string params = "DIAG_SUMMARY params source=" + source;
   params += " EntryMode=" + EntryModeText();
   params += " BiasMode=" + BiasModeText();
   params += " TrailMode=" + TrailModeText();
   params += " LongArmLevel=" + DoubleToString(LongArmLevel, 2);
   params += " ShortArmLevel=" + DoubleToString(ShortArmLevel, 2);
   params += " LookbackExtremeBars=" + IntegerToString(LookbackExtremeBars);
   params += " MaxSetupAgeBars=" + IntegerToString(MaxSetupAgeBars);
   Print(params);

   string params2 = "DIAG_SUMMARY params2 source=" + source;
   params2 += " PullbackLongLevel=" + DoubleToString(PullbackLongLevel, 2);
   params2 += " PullbackShortLevel=" + DoubleToString(PullbackShortLevel, 2);
   params2 += " PullbackLookbackBars=" + IntegerToString(PullbackLookbackBars);
   params2 += " UsePyramiding=" + usePyramidingText;
   params2 += " PyramidAccountMode=" + PyramidAccountModeText(PyramidAccountMode);
   params2 += " ActivePyramidMode=" + PyramidAccountModeText(activePyramidAccountMode);
   params2 += " MaxPyramidAdds=" + IntegerToString(MaxPyramidAdds);
   Print(params2);

   string fan = "DIAG_SUMMARY fan source=" + source;
   fan += " selection=" + FanEntrySelectionText();
   fan += " originsL=" + IntegerToString(diagFanLongOrigins);
   fan += " originsS=" + IntegerToString(diagFanShortOrigins);
   fan += " expired=" + IntegerToString(diagFanExpired);
   fan += " invalid=" + IntegerToString(diagFanInvalid);
   Print(fan);

   string fanLong = "DIAG_SUMMARY fanLong source=" + source;
   fanLong += " e1Signal=" + IntegerToString(diagFanLongE1Signals);
   fanLong += " e2Signal=" + IntegerToString(diagFanLongE2Signals);
   fanLong += " e3Signal=" + IntegerToString(diagFanLongE3Signals);
   fanLong += " e1Open=" + IntegerToString(diagFanLongE1Opened);
   fanLong += " e2Open=" + IntegerToString(diagFanLongE2Opened);
   fanLong += " e3Open=" + IntegerToString(diagFanLongE3Opened);
   Print(fanLong);

   string fanShort = "DIAG_SUMMARY fanShort source=" + source;
   fanShort += " e1Signal=" + IntegerToString(diagFanShortE1Signals);
   fanShort += " e2Signal=" + IntegerToString(diagFanShortE2Signals);
   fanShort += " e3Signal=" + IntegerToString(diagFanShortE3Signals);
   fanShort += " e1Open=" + IntegerToString(diagFanShortE1Opened);
   fanShort += " e2Open=" + IntegerToString(diagFanShortE2Opened);
   fanShort += " e3Open=" + IntegerToString(diagFanShortE3Opened);
   Print(fanShort);

   string fanParams = "DIAG_SUMMARY fanParams source=" + source;
   fanParams += " originWindow=" + IntegerToString(FanOriginCrossWindowBars);
   fanParams += " originSpread=" + DoubleToString(FanOriginMaxSpread, 2);
   fanParams += " expansion=" + DoubleToString(FanMinExpansion, 2);
   fanParams += " higherLow=" + DoubleToString(FanMinHigherLowRSI, 2);
   fanParams += " maxAge=" + IntegerToString(FanMaxAgeBars);
   fanParams += " entry2Bars=" + IntegerToString(FanEntry2MinBarsAfterEntry1);
   Print(fanParams);

   string exitProfile = "DIAG_SUMMARY exitProfile source=" + source;
   exitProfile += " use=" + (UseDirectionalExitProfile ? "true" : "false");
   exitProfile += " shortInvalidation=" + (UseShortInvalidationExit ? "true" : "false");
   exitProfile += " shortInvRSI=" + DoubleToString(ShortInvalidationRSILevel, 2);
   exitProfile += " shortInvMaxR=" + DoubleToString(ShortInvalidationMaxR, 2);
   Print(exitProfile);

   string exitProfileLong = "DIAG_SUMMARY exitProfileLong source=" + source;
   exitProfileLong += " tp1R=" + DoubleToString(TP1RFor(POSITION_TYPE_BUY), 2);
   exitProfileLong += " beR=" + DoubleToString(BreakEvenTriggerFor(POSITION_TYPE_BUY), 2);
   exitProfileLong += " trailStartR=" + DoubleToString(StartTrailingAfterFor(POSITION_TYPE_BUY), 2);
   exitProfileLong += " trailATR=" + DoubleToString(TrailATRMultiplierFor(POSITION_TYPE_BUY), 2);
   exitProfileLong += " tp2RSI=" + DoubleToString(TP2RSILevelFor(POSITION_TYPE_BUY), 2);
   exitProfileLong += " h4ExitRSI=" + DoubleToString(H4ExitRSILevelFor(POSITION_TYPE_BUY), 2);
   exitProfileLong += " tp1=" + IntegerToString(diagLongTP1);
   exitProfileLong += " tp2=" + IntegerToString(diagLongTP2);
   exitProfileLong += " h4=" + IntegerToString(diagLongH4Exit);
   exitProfileLong += " trail=" + IntegerToString(diagLongTrailUpdates);
   Print(exitProfileLong);

   string exitProfileShort = "DIAG_SUMMARY exitProfileShort source=" + source;
   exitProfileShort += " tp1R=" + DoubleToString(TP1RFor(POSITION_TYPE_SELL), 2);
   exitProfileShort += " beR=" + DoubleToString(BreakEvenTriggerFor(POSITION_TYPE_SELL), 2);
   exitProfileShort += " trailStartR=" + DoubleToString(StartTrailingAfterFor(POSITION_TYPE_SELL), 2);
   exitProfileShort += " trailATR=" + DoubleToString(TrailATRMultiplierFor(POSITION_TYPE_SELL), 2);
   exitProfileShort += " tp2RSI=" + DoubleToString(TP2RSILevelFor(POSITION_TYPE_SELL), 2);
   exitProfileShort += " h4ExitRSI=" + DoubleToString(H4ExitRSILevelFor(POSITION_TYPE_SELL), 2);
   exitProfileShort += " tp1=" + IntegerToString(diagShortTP1);
   exitProfileShort += " tp2=" + IntegerToString(diagShortTP2);
   exitProfileShort += " h4=" + IntegerToString(diagShortH4Exit);
   exitProfileShort += " invalid=" + IntegerToString(diagShortInvalidationExit);
   exitProfileShort += " trail=" + IntegerToString(diagShortTrailUpdates);
   Print(exitProfileShort);

   string longQuality = "DIAG_SUMMARY longQuality source=" + source;
   longQuality += " use=" + (UseLongQualityFilter ? "true" : "false");
   longQuality += " d1OrH4Bull=" + (LongRequireD1OrH4Bull ? "true" : "false");
   longQuality += " h4Bull=" + (LongRequireH4Bull ? "true" : "false");
   longQuality += " entryRSIMax=" + DoubleToString(LongEntryRSIMax, 2);
   longQuality += " h4RSIMin=" + DoubleToString(LongH4RSIMin, 2);
   Print(longQuality);

   string shortQuality = "DIAG_SUMMARY shortQuality source=" + source;
   shortQuality += " use=" + (UseShortQualityFilter ? "true" : "false");
   shortQuality += " d1OrH4Bear=" + (ShortRequireD1OrH4Bear ? "true" : "false");
   shortQuality += " h4Bear=" + (ShortRequireH4Bear ? "true" : "false");
   shortQuality += " entryRSIMin=" + DoubleToString(ShortEntryRSIMin, 2);
   shortQuality += " h4RSIMax=" + DoubleToString(ShortH4RSIMax, 2);
   Print(shortQuality);
}

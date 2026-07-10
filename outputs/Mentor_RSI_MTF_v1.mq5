//+------------------------------------------------------------------+
//| Mentor_RSI_MTF_v1.mq5                                            |
//| RSI multi-timeframe EA with safer risk, armed setup, diagnostics. |
//| Compile and backtest in MetaTrader 5 before any live use.        |
//+------------------------------------------------------------------+
#property strict

#include <Trade/Trade.mqh>

CTrade trade;

enum BaselineMode
{
   BL_EMA_PROXY = 0,
   BL_CUSTOM_INDICATOR = 1
};

enum EntryModeType
{
   RSI_CROSS_EMA = 0,
   RSI_ABOVE_EMA_AFTER_EXTREME = 1,
   RSI_PULLBACK_CONTINUATION = 2
};

enum BiasModeType
{
   STRICT_COUNT = 0,
   HTF_VETO = 1
};

enum TrailModeType
{
   TRAIL_OFF = 0,
   ATR_CHANDELIER = 1,
   BL_TRAIL = 2
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

input bool UseMTFBias = true;
input bool UseBLFilter = true;
input BaselineMode BLMode = BL_EMA_PROXY;
input string CustomBLIndicatorName = "";
input int CustomBLBufferIndex = 0;
input int BLFastPeriod = 70;
input int BLSlowPeriod = 150;
input double MinBLSlopePoints = 0.0;

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
input double LongNoChaseRSI = 68.0;
input double MaxDistanceFromBL_ATR = 1.5;
input bool AllowLong = true;
input bool AllowShort = true;
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
   double close1;
   double bl1;
   double bl2;
   double blFast1;
   double blFast2;
   double blSlow1;
   double blSlow2;
   double atr1;
   bool crossRSIUpEMA;
   bool crossRSIDownEMA;
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

ENUM_TIMEFRAMES DataTFs[4] = { PERIOD_D1, PERIOD_H4, PERIOD_H1, PERIOD_M15 };
int rsiHandles[4];
int blFastHandles[4];
int blSlowHandles[4];
int blCustomHandles[4];
int atrHandles[4];

datetime lastEntryBarTime = 0;
ulong managedTicket = 0;
bool tp1Done = false;
bool tp2Done = false;
double initialPositionVolume = 0.0;
double managedInitialRiskDistance = 0.0;

int armedLongBars = 0;
int armedShortBars = 0;

int diagArmedLong = 0;
int diagArmedShort = 0;
int diagRejectBias = 0;
int diagRejectBL = 0;
int diagRejectChop = 0;
int diagRejectRisk = 0;
int diagRejectCurl = 0;
int diagRejectCross = 0;
int diagRejectEMASide = 0;
int diagRejectVolume = 0;
int diagRejectLongNoChase = 0;
int diagRejectLongFarFromBL = 0;
int diagTrailExit = 0;
int diagEntryBars = 0;
int diagTradesOpened = 0;
int diagLongOpened = 0;
int diagShortOpened = 0;
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

   for(int i = 0; i < 4; i++)
   {
      rsiHandles[i] = iRSI(_Symbol, DataTFs[i], RSIPeriod, PRICE_CLOSE);
      blFastHandles[i] = iMA(_Symbol, DataTFs[i], BLFastPeriod, 0, MODE_EMA, PRICE_CLOSE);
      blSlowHandles[i] = iMA(_Symbol, DataTFs[i], BLSlowPeriod, 0, MODE_EMA, PRICE_CLOSE);
      atrHandles[i] = iATR(_Symbol, DataTFs[i], ATRPeriod);
      blCustomHandles[i] = INVALID_HANDLE;

      if(BLMode == BL_CUSTOM_INDICATOR && CustomBLIndicatorName != "")
         blCustomHandles[i] = iCustom(_Symbol, DataTFs[i], CustomBLIndicatorName);

      if(rsiHandles[i] == INVALID_HANDLE || blFastHandles[i] == INVALID_HANDLE || blSlowHandles[i] == INVALID_HANDLE || atrHandles[i] == INVALID_HANDLE)
      {
         Print("Failed to create core indicator handles for ", TFName(DataTFs[i]));
         return INIT_FAILED;
      }

      if(BLMode == BL_CUSTOM_INDICATOR && CustomBLIndicatorName != "" && blCustomHandles[i] == INVALID_HANDLE)
      {
         Print("Custom BL unavailable on ", TFName(DataTFs[i]), ". Using EMA70/150 proxy for this run.");
      }
   }

   if(BLMode == BL_EMA_PROXY || CustomBLIndicatorName == "")
      Print("BL mode: EMA proxy. This is not the mentor custom BL unless the proxy has been validated.");
   else
      Print("BL mode: custom indicator=", CustomBLIndicatorName, " buffer=", CustomBLBufferIndex);

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

   if(ExportDiagnosticsCsv)
   {
      diagCsvHandle = FileOpen("Mentor_RSI_MTF_diag.csv", FILE_WRITE | FILE_CSV | FILE_ANSI);
      if(diagCsvHandle != INVALID_HANDLE)
      {
         FileWrite(diagCsvHandle, "time", "entry_tf", "entry_mode", "bias_mode", "armed_long", "armed_short",
                   "bias_bull", "bias_bear", "reject_bias", "reject_bl", "reject_chop",
                   "reject_risk", "reject_curl", "reject_cross", "reject_ema_side",
                   "reject_volume", "reject_long_no_chase", "reject_long_far_from_bl",
                   "entry_distance_bl_atr", "entry_state", "snapshot");
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
      if(blFastHandles[i] != INVALID_HANDLE)
         IndicatorRelease(blFastHandles[i]);
      if(blSlowHandles[i] != INVALID_HANDLE)
         IndicatorRelease(blSlowHandles[i]);
      if(atrHandles[i] != INVALID_HANDLE)
         IndicatorRelease(atrHandles[i]);
      if(blCustomHandles[i] != INVALID_HANDLE)
         IndicatorRelease(blCustomHandles[i]);
   }
}

double OnTester()
{
   PrintDiagnosticsSummary("OnTester");
   return 0.0;
}

void OnTick()
{
   ManageOpenPosition();

   datetime barTime = iTime(_Symbol, EntryTF, 0);
   if(barTime == lastEntryBarTime)
      return;
   lastEntryBarTime = barTime;

   if(HasOpenPosition())
      return;

   TFState d1, h4, h1, m15, entry;
   if(!BuildState(PERIOD_D1, d1) || !BuildState(PERIOD_H4, h4) || !BuildState(PERIOD_H1, h1) || !BuildState(PERIOD_M15, m15))
      return;
   if(!BuildState(EntryTF, entry))
      return;

   diagEntryBars++;
   UpdateArmedState(entry);

   int bullCount = 0;
   int bearCount = 0;
   CountBias(d1, bullCount, bearCount);
   CountBias(h4, bullCount, bearCount);
   CountBias(h1, bullCount, bearCount);

   bool longBias = BiasAllowsLong(d1, h4, h1, bullCount);
   bool shortBias = BiasAllowsShort(d1, h4, h1, bearCount);

   string reject = "";
   if(AllowLong && LongSignal(entry, h4, longBias, reject))
   {
      OpenTrade(ORDER_TYPE_BUY, entry, d1, h4, h1, m15);
      if(HasOpenPosition())
         return;
   }
   else if(AllowLong && LongSetupActive(entry))
      TrackReject(reject);

   reject = "";
   if(AllowShort && ShortSignal(entry, h4, shortBias, reject))
      OpenTrade(ORDER_TYPE_SELL, entry, d1, h4, h1, m15);
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
   double blFast[];
   double blSlow[];
   double blCustom[];
   double atr[];
   MqlRates rates[];
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(blFast, true);
   ArraySetAsSeries(blSlow, true);
   ArraySetAsSeries(blCustom, true);
   ArraySetAsSeries(atr, true);
   ArraySetAsSeries(rates, true);

   if(CopyBuffer(rsiHandles[idx], 0, 0, need, rsi) < need)
      return false;
   if(CopyBuffer(blFastHandles[idx], 0, 0, need, blFast) < need)
      return false;
   if(CopyBuffer(blSlowHandles[idx], 0, 0, need, blSlow) < need)
      return false;
   if(CopyBuffer(atrHandles[idx], 0, 0, need, atr) < need)
      return false;
   if(CopyRates(_Symbol, tf, 0, need, rates) < need)
      return false;

   bool customBLReady = false;
   if(BLMode == BL_CUSTOM_INDICATOR && blCustomHandles[idx] != INVALID_HANDLE)
      customBLReady = (CopyBuffer(blCustomHandles[idx], CustomBLBufferIndex, 0, need, blCustom) >= need);

   s.tf = tf;
   s.rsi1 = rsi[1];
   s.rsi2 = rsi[2];
   s.ema1 = EMAOnSeries(rsi, RSI_EMA_Period, 1, need);
   s.ema2 = EMAOnSeries(rsi, RSI_EMA_Period, 2, need);
   s.wma1 = WMAOnSeries(rsi, RSI_WMA_Period, 1, need);
   s.wma2 = WMAOnSeries(rsi, RSI_WMA_Period, 2, need);
   s.close1 = rates[1].close;
   s.blFast1 = blFast[1];
   s.blFast2 = blFast[2];
   s.blSlow1 = blSlow[1];
   s.blSlow2 = blSlow[2];
   s.bl1 = customBLReady ? blCustom[1] : blFast[1];
   s.bl2 = customBLReady ? blCustom[2] : blFast[2];
   s.atr1 = atr[1];
   s.crossRSIUpEMA = (s.rsi2 <= s.ema2 && s.rsi1 > s.ema1);
   s.crossRSIDownEMA = (s.rsi2 >= s.ema2 && s.rsi1 < s.ema1);
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

BiasState GetBias(const TFState &s)
{
   double minSlope = MinBLSlopePoints * _Point;
   bool blUp = (s.close1 > s.bl1 && s.bl1 - s.bl2 >= minSlope);
   bool blDown = (s.close1 < s.bl1 && s.bl2 - s.bl1 >= minSlope);
   bool rsiBull = (s.rsi1 > s.ema1 && s.ema1 >= s.wma1 && s.wma1 >= s.wma2);
   bool rsiBear = (s.rsi1 < s.ema1 && s.ema1 <= s.wma1 && s.wma1 <= s.wma2);

   if(rsiBull && (!UseBLFilter || blUp))
      return BIAS_BULL;
   if(rsiBear && (!UseBLFilter || blDown))
      return BIAS_BEAR;

   return BIAS_NEUTRAL;
}

bool IsChop(const TFState &s)
{
   if(!UseChopFilter)
      return false;

   bool rsiMid = (s.rsi1 >= ChopMinRSI && s.rsi1 <= ChopMaxRSI);
   bool maTight = (MathAbs(s.ema1 - s.wma1) <= ChopMAProximity);
   bool blFlat = (MathAbs(s.bl1 - s.bl2) <= MinBLSlopePoints * _Point);
   return (rsiMid && maTight && blFlat);
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

double DistanceFromBLInATR(const TFState &s)
{
   if(s.atr1 <= 0.0)
      return 0.0;
   return MathAbs(s.close1 - s.bl1) / s.atr1;
}

bool LongNoChasePass(const TFState &entry, const TFState &h4, string &reject)
{
   double entryDistance = DistanceFromBLInATR(entry);
   double h4Distance = DistanceFromBLInATR(h4);

   if(MaxDistanceFromBL_ATR > 0.0 && entry.close1 > entry.bl1 && entryDistance > MaxDistanceFromBL_ATR)
   {
      reject = "long_far_from_bl";
      return false;
   }

   if(MaxDistanceFromBL_ATR > 0.0 && h4.rsi1 >= LongNoChaseRSI && h4.close1 > h4.bl1 && h4Distance > MaxDistanceFromBL_ATR)
   {
      reject = "long_no_chase";
      return false;
   }

   return true;
}

bool LongSetupActive(const TFState &entry)
{
   if(EntryMode == RSI_PULLBACK_CONTINUATION)
      return (armedLongBars > 0 || entry.pullbackLongRecent);
   return (armedLongBars > 0);
}

bool ShortSetupActive(const TFState &entry)
{
   if(EntryMode == RSI_PULLBACK_CONTINUATION)
      return (armedShortBars > 0 || entry.pullbackShortRecent);
   return (armedShortBars > 0);
}

bool LongSignal(const TFState &entry, const TFState &h4, bool biasOK, string &reject)
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
   if(UseBLFilter && entry.close1 < entry.bl1 && entry.bl1 < entry.bl2)
   {
      reject = "bl";
      return false;
   }
   if(!LongNoChasePass(entry, h4, reject))
      return false;

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

   if(entry.rsi1 > entry.ema1)
   {
      reject = "";
      return true;
   }

   reject = "ema_side";
   return false;
}

bool ShortSignal(const TFState &entry, const TFState &h4, bool biasOK, string &reject)
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
   if(UseBLFilter && entry.close1 > entry.bl1 && entry.bl1 > entry.bl2)
   {
      reject = "bl";
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

bool HasOpenPosition()
{
   if(!PositionSelect(_Symbol))
      return false;
   return ((int)PositionGetInteger(POSITION_MAGIC) == MagicNumber);
}

void OpenTrade(ENUM_ORDER_TYPE type, const TFState &entry, const TFState &d1, const TFState &h4, const TFState &h1, const TFState &m15)
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
   bool ok = false;
   if(type == ORDER_TYPE_BUY)
      ok = trade.Buy(rp.lots, _Symbol, price, sl, tp, comment);
   else
      ok = trade.Sell(rp.lots, _Symbol, price, sl, tp, comment);

   if(ok)
   {
      managedTicket = (ulong)trade.ResultOrder();
      tp1Done = false;
      tp2Done = false;
      initialPositionVolume = rp.lots;
      managedInitialRiskDistance = riskDistance;
      armedLongBars = 0;
      armedShortBars = 0;
      diagTradesOpened++;
      if(type == ORDER_TYPE_BUY)
         diagLongOpened++;
      else
         diagShortOpened++;
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

void ManageOpenPosition()
{
   if(!PositionSelect(_Symbol))
   {
      managedTicket = 0;
      tp1Done = false;
      tp2Done = false;
      initialPositionVolume = 0.0;
      managedInitialRiskDistance = 0.0;
      return;
   }
   if((int)PositionGetInteger(POSITION_MAGIC) != MagicNumber)
      return;

   ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
   if(managedTicket != ticket)
   {
      managedTicket = ticket;
      tp1Done = false;
      tp2Done = false;
      initialPositionVolume = PositionGetDouble(POSITION_VOLUME);
      managedInitialRiskDistance = MathAbs(PositionGetDouble(POSITION_PRICE_OPEN) - PositionGetDouble(POSITION_SL));
   }

   long positionType = PositionGetInteger(POSITION_TYPE);
   double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   double volume = PositionGetDouble(POSITION_VOLUME);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double current = (positionType == POSITION_TYPE_BUY) ? bid : ask;
   double initialRisk = managedInitialRiskDistance;
   if(initialRisk <= _Point)
      initialRisk = MathAbs(entryPrice - sl);

   if(initialRisk <= _Point)
      return;

   double profitDistance = (positionType == POSITION_TYPE_BUY) ? current - entryPrice : entryPrice - current;
   double rMultiple = profitDistance / initialRisk;

   if(rMultiple >= BreakEvenTriggerR)
      MoveSLToBreakEven(positionType, entryPrice, sl, tp);

   if(UsePartialExits && !tp1Done && rMultiple >= TP1_R)
   {
      if(ClosePartial(volume, TP1ClosePct, "TP1"))
      {
         tp1Done = true;
         MoveSLToBreakEven(positionType, entryPrice, PositionGetDouble(POSITION_SL), PositionGetDouble(POSITION_TP));
      }
   }

   sl = PositionGetDouble(POSITION_SL);
   tp = PositionGetDouble(POSITION_TP);

   TFState entryState, h1, h4;
   if(!BuildState(EntryTF, entryState) || !BuildState(PERIOD_H1, h1) || !BuildState(PERIOD_H4, h4))
      return;

   if(TrailMode != TRAIL_OFF && rMultiple >= StartTrailingAfterR)
      ApplyTrailingStop(positionType, sl, tp, entryState);

   bool entryExitLong = (entryState.rsi2 >= 65.0 && entryState.rsi1 < entryState.rsi2 && entryState.crossRSIDownEMA);
   bool h1ExitLong = (h1.rsi2 >= 65.0 && h1.rsi1 < h1.rsi2 && h1.crossRSIDownEMA);
   bool entryExitShort = (entryState.rsi2 <= 35.0 && entryState.rsi1 > entryState.rsi2 && entryState.crossRSIUpEMA);
   bool h1ExitShort = (h1.rsi2 <= 35.0 && h1.rsi1 > h1.rsi2 && h1.crossRSIUpEMA);

   if(UsePartialExits && tp1Done && !tp2Done)
   {
      bool tp2Signal = (positionType == POSITION_TYPE_BUY) ? (entryExitLong || h1ExitLong) : (entryExitShort || h1ExitShort);
      if(tp2Signal && ClosePartial(PositionGetDouble(POSITION_VOLUME), TP2ClosePct, "TP2_RSI"))
         tp2Done = true;
   }

   if(positionType == POSITION_TYPE_BUY)
   {
      bool h4Exit = (h4.rsi2 > Overbought && h4.rsi1 < h4.rsi2 && h4.crossRSIDownEMA);
      bool blExit = (UseBLFilter && h4.close1 < h4.bl1);
      if(h4Exit || blExit)
         trade.PositionClose(_Symbol);
   }
   else
   {
      bool h4Exit = (h4.rsi2 < Oversold && h4.rsi1 > h4.rsi2 && h4.crossRSIUpEMA);
      bool blExit = (UseBLFilter && h4.close1 > h4.bl1);
      if(h4Exit || blExit)
         trade.PositionClose(_Symbol);
   }
}

void MoveSLToBreakEven(long positionType, double entryPrice, double currentSL, double tp)
{
   double beSL = (positionType == POSITION_TYPE_BUY) ? entryPrice + 2 * _Point : entryPrice - 2 * _Point;
   bool improve = (positionType == POSITION_TYPE_BUY && beSL > currentSL) || (positionType == POSITION_TYPE_SELL && beSL < currentSL);
   if(improve)
      trade.PositionModify(_Symbol, NormalizeDouble(beSL, _Digits), tp);
}

void ApplyTrailingStop(long positionType, double currentSL, double tp, const TFState &entryState)
{
   double trailSL = 0.0;

   if(TrailMode == ATR_CHANDELIER)
      trailSL = ChandelierTrailSL(positionType, entryState.atr1);
   else if(TrailMode == BL_TRAIL)
      trailSL = entryState.bl1;

   if(trailSL <= 0.0)
      return;

   trailSL = NormalizeDouble(trailSL, _Digits);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(positionType == POSITION_TYPE_BUY && trailSL >= bid)
      return;
   if(positionType == POSITION_TYPE_SELL && trailSL <= ask)
      return;

   bool improve = (positionType == POSITION_TYPE_BUY && trailSL > currentSL) || (positionType == POSITION_TYPE_SELL && trailSL < currentSL);
   if(improve && trade.PositionModify(_Symbol, trailSL, tp))
   {
      diagTrailExit++;
      Print("TRAIL update mode=", TrailModeText(), " sl=", DoubleToString(trailSL, _Digits));
   }
}

double ChandelierTrailSL(long positionType, double atr)
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
      return highest - atr * TrailATRMultiplier;
   }

   double lowest = rates[1].low;
   for(int i = 2; i <= TrailLookbackBars; i++)
      lowest = MathMin(lowest, rates[i].low);
   return lowest + atr * TrailATRMultiplier;
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

string TrailModeText()
{
   if(TrailMode == ATR_CHANDELIER)
      return "ATR_CHANDELIER";
   if(TrailMode == BL_TRAIL)
      return "BL_TRAIL";
   return "OFF";
}

string EntryModeText()
{
   if(EntryMode == RSI_CROSS_EMA)
      return "RSI_CROSS_EMA";
   if(EntryMode == RSI_PULLBACK_CONTINUATION)
      return "RSI_PULLBACK_CONTINUATION";
   return "RSI_ABOVE_EMA_AFTER_EXTREME";
}

string StateText(const TFState &s)
{
   return TFName(s.tf) + ":RSI=" + DoubleToString(s.rsi1, 2) +
          ",EMA=" + DoubleToString(s.ema1, 2) +
          ",WMA=" + DoubleToString(s.wma1, 2) +
          ",BL=" + DoubleToString(s.bl1, _Digits) +
          ",ATR=" + DoubleToString(s.atr1, _Digits) +
          ",DistBL_ATR=" + DoubleToString(DistanceFromBLInATR(s), 2) +
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
   else if(reason == "bl")
      diagRejectBL++;
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
   else if(reason == "long_no_chase")
      diagRejectLongNoChase++;
   else if(reason == "long_far_from_bl")
      diagRejectLongFarFromBL++;
}

void PrintDiagnostics(const TFState &d1, const TFState &h4, const TFState &h1, const TFState &m15, const TFState &entry, int bullCount, int bearCount)
{
   if(!Diagnostics)
      return;

   bool shouldPrint = (DiagnosticsEveryBars <= 1 || diagEntryBars % DiagnosticsEveryBars == 0);
   string entryModeText = EntryModeText();
   string biasModeText = BiasModeText();
   string snapshot = Snapshot(d1, h4, h1, m15);
   double entryDistance = DistanceFromBLInATR(entry);

   if(diagCsvHandle != INVALID_HANDLE)
   {
      FileWrite(diagCsvHandle, TimeToString(lastEntryBarTime), TFName(EntryTF), entryModeText, biasModeText,
                armedLongBars, armedShortBars, bullCount, bearCount, diagRejectBias,
                diagRejectBL, diagRejectChop, diagRejectRisk, diagRejectCurl,
                diagRejectCross, diagRejectEMASide, diagRejectVolume, diagRejectLongNoChase,
                diagRejectLongFarFromBL, DoubleToString(entryDistance, 2), StateText(entry), snapshot);
   }

   if(!shouldPrint)
      return;

   Print("DIAG bar=", TimeToString(lastEntryBarTime),
         " entryTF=", TFName(EntryTF),
         " mode=", entryModeText,
         " biasMode=", biasModeText,
         " armedL=", armedLongBars,
         " armedS=", armedShortBars,
         " biasBull=", bullCount,
         " biasBear=", bearCount,
         " rejects[bias=", diagRejectBias,
         ",bl=", diagRejectBL,
         ",chop=", diagRejectChop,
         ",risk=", diagRejectRisk,
         ",curl=", diagRejectCurl,
         ",cross=", diagRejectCross,
         ",emaSide=", diagRejectEMASide,
         ",volume=", diagRejectVolume,
         ",longNoChase=", diagRejectLongNoChase,
         ",longFarBL=", diagRejectLongFarFromBL,
         "] entry=", StateText(entry),
         " entryDistBL_ATR=", DoubleToString(entryDistance, 2),
         " snapshot=", snapshot);
}

void PrintDiagnosticsSummary(string source)
{
   Print("DIAG_SUMMARY source=", source,
         " bars=", diagEntryBars,
         " trades=", diagTradesOpened,
         " longTrades=", diagLongOpened,
         " shortTrades=", diagShortOpened,
         " armedLong=", diagArmedLong,
         " armedShort=", diagArmedShort,
         " rejects[bias=", diagRejectBias,
         ",bl=", diagRejectBL,
         ",chop=", diagRejectChop,
         ",risk=", diagRejectRisk,
         ",curl=", diagRejectCurl,
         ",cross=", diagRejectCross,
         ",emaSide=", diagRejectEMASide,
         ",volume=", diagRejectVolume,
         ",longNoChase=", diagRejectLongNoChase,
         ",longFarBL=", diagRejectLongFarFromBL,
         ",trailUpdates=", diagTrailExit,
         "] EntryMode=", EntryModeText(),
         " BiasMode=", BiasModeText(),
         " TrailMode=", TrailModeText(),
         " LongArmLevel=", LongArmLevel,
         " ShortArmLevel=", ShortArmLevel,
         " LookbackExtremeBars=", LookbackExtremeBars,
         " MaxSetupAgeBars=", MaxSetupAgeBars,
         " PullbackLongLevel=", PullbackLongLevel,
         " PullbackShortLevel=", PullbackShortLevel,
         " PullbackLookbackBars=", PullbackLookbackBars);
}

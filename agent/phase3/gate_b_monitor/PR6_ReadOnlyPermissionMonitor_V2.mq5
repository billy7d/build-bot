#property strict
#property version   "2.0"
#property description "PR #6 read-only permission monitor V2; controller-bound, no trade or file APIs."

// This EA is intentionally read-only.  The independent supervisor supplies
// the session/chart binding and owns chart cleanup; this EA never closes a
// chart or a terminal.
input long InpExpectedAccount = 414060440;
input string InpExpectedServer = "Exness-MT5Trial6";
input string InpExpectedSymbol = "BTCUSD";
input ENUM_TIMEFRAMES InpExpectedTimeframe = PERIOD_H1;
input long InpExpectedChartId = -1;
input string InpSessionId = "";
input string InpStartUtc = "";
input string InpExpectedSourceSha256 = "";
input string InpExpectedEx5Sha256 = "";
input string InpApprovalRef = "";

const ulong SAMPLE_INTERVAL_MS = 60000;
const ulong SOFT_STOP_MS = 540000;

ulong g_started_monotonic_ms = 0;
ulong g_next_sample_monotonic_ms = 0;
bool g_initialized = false;

string UtcIso()
{
   string value = TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS);
   StringReplace(value, ".", "-");
   StringReplace(value, " ", "T");
   return value + "Z";
}

bool IdentityMatches()
{
   if(AccountInfoInteger(ACCOUNT_LOGIN) != InpExpectedAccount)
      return false;
   if(AccountInfoString(ACCOUNT_SERVER) != InpExpectedServer)
      return false;
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
      return false;
   if(AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) != 0)
      return false;
   if(TerminalInfoInteger(TERMINAL_CONNECTED) != 1)
      return false;
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) != 0)
      return false;
   if(_Symbol != InpExpectedSymbol || Period() != InpExpectedTimeframe)
      return false;
   if(InpExpectedChartId <= 0 || ChartID() != InpExpectedChartId)
      return false;
   if(StringLen(InpSessionId) == 0 || StringLen(InpStartUtc) == 0)
      return false;
   if(MQLInfoInteger(MQL_PROGRAM_TYPE) != 2)
      return false;
   return true;
}

void EmitSnapshot(const string reason)
{
   const long account_login = AccountInfoInteger(ACCOUNT_LOGIN);
   const string account_server = AccountInfoString(ACCOUNT_SERVER);
   const long account_trade_mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   const long account_trade_allowed = AccountInfoInteger(ACCOUNT_TRADE_ALLOWED);
   const long account_trade_expert = AccountInfoInteger(ACCOUNT_TRADE_EXPERT);
   const long terminal_connected = TerminalInfoInteger(TERMINAL_CONNECTED);
   const long terminal_trade_allowed = TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
   const long mql_trade_allowed = MQLInfoInteger(MQL_TRADE_ALLOWED);
   const long mql_program_type = MQLInfoInteger(MQL_PROGRAM_TYPE);
   const long chart_id = ChartID();
   const ulong monotonic_ms = GetTickCount64();

   PrintFormat(
      "PR6_READ_ONLY_PERMISSION_MONITOR_V2/1 session_id=%s timestamp_utc=%s monotonic_ms=%I64u account=%I64d server=%s symbol=%s timeframe=H1 chart_id=%I64d account_trade_mode=%I64d account_trade_allowed=%I64d account_trade_expert=%I64d terminal_connected=%I64d terminal_trade_allowed=%I64d mql_trade_allowed=%I64d mql_program_type=%I64d scope=monitor_ea reason=%s",
      InpSessionId,
      UtcIso(),
      monotonic_ms,
      account_login,
      account_server,
      _Symbol,
      chart_id,
      account_trade_mode,
      account_trade_allowed,
      account_trade_expert,
      terminal_connected,
      terminal_trade_allowed,
      mql_trade_allowed,
      mql_program_type,
      reason
   );
}

void RequestRemoval(const string reason)
{
   PrintFormat(
      "PR6_READ_ONLY_PERMISSION_MONITOR_V2/1_STOP_REQUEST session_id=%s timestamp_utc=%s monotonic_ms=%I64u reason=%s",
      InpSessionId,
      UtcIso(),
      GetTickCount64(),
      reason
   );
   ExpertRemove();
}

int OnInit()
{
   if(!IdentityMatches())
   {
      PrintFormat("PR6_READ_ONLY_PERMISSION_MONITOR_V2/1_INIT_REJECT session_id=%s reason=IDENTITY_OR_PERMISSION_MISMATCH", InpSessionId);
      return INIT_PARAMETERS_INCORRECT;
   }
   if(!EventSetTimer(1))
   {
      PrintFormat("PR6_READ_ONLY_PERMISSION_MONITOR_V2/1_INIT_REJECT session_id=%s reason=TIMER_REGISTRATION_FAILED", InpSessionId);
      return INIT_FAILED;
   }
   g_started_monotonic_ms = GetTickCount64();
   g_next_sample_monotonic_ms = g_started_monotonic_ms + SAMPLE_INTERVAL_MS;
   g_initialized = true;
   EmitSnapshot("INITIAL");
   return INIT_SUCCEEDED;
}

void OnTimer()
{
   if(!g_initialized)
      return;
   const ulong now_monotonic_ms = GetTickCount64();
   if(now_monotonic_ms < g_started_monotonic_ms)
   {
      RequestRemoval("MONOTONIC_CLOCK_ROLLOVER");
      return;
   }
   const ulong elapsed_ms = now_monotonic_ms - g_started_monotonic_ms;
   if(!IdentityMatches())
   {
      RequestRemoval("IDENTITY_PERMISSION_OR_CONNECTION_CHANGED");
      return;
   }
   if(elapsed_ms >= SOFT_STOP_MS)
   {
      RequestRemoval("SOFT_DEADLINE_540_SECONDS");
      return;
   }
   if(now_monotonic_ms >= g_next_sample_monotonic_ms)
   {
      EmitSnapshot("PERIODIC");
      g_next_sample_monotonic_ms = now_monotonic_ms + SAMPLE_INTERVAL_MS;
   }
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   PrintFormat(
      "PR6_READ_ONLY_PERMISSION_MONITOR_V2/1_DEINIT session_id=%s timestamp_utc=%s monotonic_ms=%I64u reason=%d",
      InpSessionId,
      UtcIso(),
      GetTickCount64(),
      reason
   );
}

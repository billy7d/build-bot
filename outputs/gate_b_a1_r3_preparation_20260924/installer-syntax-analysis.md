# A1-R3 installer argument analysis

Status: `INSTALLER_ARGUMENT_SYNTAX_VERIFIED`; no installer was executed in A1-R3 preparation.

MetaQuotes documents unattended installation as `/auto` and permits selecting a destination with `/path:"..."`; its example places the quoted path immediately after `/path:`. See [MetaTrader 5 installation options](https://www.metatrader5.com/en/terminal/help/start_advanced/installation).

The prior PowerShell runner assembled the `/path` value as three `Start-Process -ArgumentList` array elements: `/path:"`, the destination, and `"`. Microsoft documents that `Start-Process` joins an `ArgumentList` array into a single space-separated argument string and notes that embedded quotes must be included in the argument text. Splitting the option and its quote boundaries therefore caused whitespace to be inserted inside the quoted path value, rather than passing one intact `/path:"D:\Trading\MT5-GateB-Acceptance"` argument. See [Microsoft `Start-Process` documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/start-process?view=powershell-7.5).

The non-installing echo probe recorded in the preserved A1-R evidence returned:

```text
/auto /path:"D:\Trading\MT5-GateB-Acceptance"
PowerShell argument array items: /auto ; /path:"D:\Trading\MT5-GateB-Acceptance"
```

The corrected argument construction is exactly two array elements, with the complete `/path:"..."` value held in one element:

```powershell
$destination = 'D:\Trading\MT5-GateB-Acceptance'
$arguments = @('/auto', ('/path:"' + $destination + '"'))
Start-Process -FilePath 'D:\mt5setup.exe' -ArgumentList $arguments -Wait -PassThru
```

The resulting command line is:

```text
"D:\mt5setup.exe" /auto /path:"D:\Trading\MT5-GateB-Acceptance"
```

This verifies option spelling, quoting, and PowerShell argument construction from the vendor syntax plus the saved echo probe; it is not evidence of a successful installation. Before any reinstall, recheck `D:\mt5setup.exe` SHA-256, Authenticode status, signer, and version against the approval's recorded expected values. Reinstall remains unauthorized until Operator cleanup evidence and Codex's independent wrong-root/V26 verification pass.

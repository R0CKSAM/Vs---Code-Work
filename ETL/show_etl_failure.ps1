param([Parameter(Mandatory=$true)][string]$AlertFile)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$alert = Get-Content -LiteralPath $AlertFile -Raw | ConvertFrom-Json
$form = New-Object Windows.Forms.Form
$form.Text = 'Veto ETL - Action Required'
$form.Size = New-Object Drawing.Size(660, 350)
$form.MinimumSize = $form.Size
$form.StartPosition = 'CenterScreen'
$form.TopMost = $true
$form.Icon = [Drawing.SystemIcons]::Error
$form.Font = New-Object Drawing.Font('Segoe UI', 10)
$form.Padding = New-Object Windows.Forms.Padding(16)
$form.BackColor = [Drawing.Color]::White
$heading = New-Object Windows.Forms.Label
$heading.Text = "ETL needs attention`r`n$($alert.step)"
$heading.AutoSize = $false
$heading.Height = 68
$heading.Dock = 'Top'
$heading.Font = New-Object Drawing.Font('Segoe UI', 12, ([Drawing.FontStyle]::Bold))
$message = New-Object Windows.Forms.TextBox
$message.Multiline = $true
$message.ReadOnly = $true
$message.ScrollBars = 'Vertical'
$message.Dock = 'Fill'
$message.Text = "$($alert.created_at)`r`n`r`n$($alert.error)"
$buttons = New-Object Windows.Forms.FlowLayoutPanel
$buttons.Dock = 'Bottom'
$buttons.Height = 48
$buttons.FlowDirection = 'LeftToRight'
foreach ($label in @('Open Log', 'Open Status', 'Dismiss')) {
    $button = New-Object Windows.Forms.Button
    $button.Text = $label
    $button.Size = New-Object Drawing.Size(125, 34)
    if ($label -eq 'Open Log') {
        $button.Enabled = [bool]($alert.log_path -and (Test-Path -LiteralPath $alert.log_path -PathType Leaf))
        $button.Add_Click({ Start-Process -FilePath 'notepad.exe' -ArgumentList ('"{0}"' -f $alert.log_path) -WindowStyle Normal })
    } elseif ($label -eq 'Open Status') {
        $button.Enabled = [bool]($alert.state_path -and (Test-Path -LiteralPath $alert.state_path -PathType Leaf))
        $button.Add_Click({ Start-Process -FilePath 'notepad.exe' -ArgumentList ('"{0}"' -f $alert.state_path) -WindowStyle Normal })
    } else {
        $button.Add_Click({
            $alert.acknowledged = $true
            $alert | ConvertTo-Json | Set-Content -LiteralPath $AlertFile -Encoding UTF8
            $form.Close()
        })
    }
    $buttons.Controls.Add($button)
}
$form.Controls.Add($message)
$form.Controls.Add($buttons)
$form.Controls.Add($heading)
$form.Add_Shown({
    (Get-Date).ToString('o') | Set-Content -LiteralPath ($AlertFile + '.shown') -Encoding UTF8
    $form.Activate()
})
[void]$form.ShowDialog()
$form.Dispose()

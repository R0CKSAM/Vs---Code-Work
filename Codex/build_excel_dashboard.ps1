param(
    [string]$CsvPath = "D:\Raj\CTV FCT.csv",
    [string]$OutputPath = "D:\Raj\Codex\CTV FCT Dashboard.xlsx"
)

$ErrorActionPreference = "Stop"

function Release-ComObject {
    param([Parameter(ValueFromPipeline = $true)]$ComObject)
    process {
        if ($null -ne $ComObject) {
            try {
                [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($ComObject)
            } catch {
            }
        }
    }
}

function Set-SectionHeader {
    param(
        $Sheet,
        [string]$RangeAddress,
        [string]$Text
    )

    $range = $Sheet.Range($RangeAddress)
    $range.Merge()
    $range.Value2 = $Text
    $range.Interior.Color = 2105376
    $range.Font.Color = 16777215
    $range.Font.Bold = $true
    $range.Font.Size = 12
    $range.HorizontalAlignment = -4131
    $range.VerticalAlignment = -4108
}

function Format-Grid {
    param(
        $Sheet,
        [string]$RangeAddress
    )

    $range = $Sheet.Range($RangeAddress)
    $range.Borders.LineStyle = 1
    $range.Borders.Color = 14540253
    $range.Font.Name = "Segoe UI"
    $range.Font.Size = 9
}

if (-not (Test-Path -LiteralPath $CsvPath)) {
    throw "CSV file not found: $CsvPath"
}

$excludedCategories = @(
    "ASTROLOGERS",
    "CHANNEL IMAGERY",
    "PROMO CHANNEL PROPERTIES",
    "PROMO CHANNEL/BRAND",
    "PROMO PROGRAM",
    "PROMO TAG",
    "SHORT PROGRAM",
    "TELEVISIONS"
)

$xlDatabase = 1
$xlYes = 1
$xlSheetHidden = 0
$xlRowField = 1
$xlColumnField = 2
$xlPageField = 3
$xlSum = -4157
$xlCount = -4112
$xlTabularRow = 1
$xlDescending = 2
$xlColumnClustered = 51
$xlBarClustered = 57
$xlLine = 4
$xlDataLabelShowValue = 2
$xlMissing = [Type]::Missing
$xlSourceTypeDatabase = 1
$xlPivotTableVersion15 = 6

$excel = $null
$workbook = $null

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false

    $workbook = $excel.Workbooks.Add()
    while ($workbook.Worksheets.Count -lt 6) {
        [void]$workbook.Worksheets.Add()
    }

    $dataSheet = $workbook.Worksheets.Item(1)
    $dataSheet.Name = "Data"
    $dashboardSheet = $workbook.Worksheets.Item(2)
    $dashboardSheet.Name = "Dashboard"
    $pivotSheet = $workbook.Worksheets.Item(3)
    $pivotSheet.Name = "Pivots"
    $listsSheet = $workbook.Worksheets.Item(4)
    $listsSheet.Name = "Lists"
    $pivotChannelSheet = $workbook.Worksheets.Item(5)
    $pivotChannelSheet.Name = "PivotChannel"
    $pivotDateSheet = $workbook.Worksheets.Item(6)
    $pivotDateSheet.Name = "PivotDate"

    for ($idx = $workbook.Worksheets.Count; $idx -ge 7; $idx--) {
        $workbook.Worksheets.Item($idx).Delete()
    }

    $queryTable = $dataSheet.QueryTables.Add("TEXT;$CsvPath", $dataSheet.Range("A1"))
    $queryTable.TextFileParseType = 1
    $queryTable.TextFileCommaDelimiter = $true
    $queryTable.TextFilePlatform = 65001
    $queryTable.TextFileTextQualifier = 1
    $queryTable.AdjustColumnWidth = $true
    $queryTable.Refresh($false)
    $queryTable.Delete()

    $usedRange = $dataSheet.UsedRange
    $headerMap = @{}
    for ($col = 1; $col -le $usedRange.Columns.Count; $col++) {
        $header = [string]$dataSheet.Cells.Item(1, $col).Value2
        if ($header) {
            $headerMap[$header] = $col
        }
    }

    if ($headerMap.ContainsKey("Feed Name")) {
        $feedCol = $headerMap["Feed Name"]
        if ($headerMap.ContainsKey("Channel Name")) {
            $channelCol = $headerMap["Channel Name"]
            if ($lastRow -ge 2) {
                $sourceRange = $dataSheet.Range($dataSheet.Cells.Item(2, $feedCol), $dataSheet.Cells.Item($lastRow, $feedCol))
                $targetRange = $dataSheet.Range($dataSheet.Cells.Item(2, $channelCol), $dataSheet.Cells.Item($lastRow, $channelCol))
                $targetRange.Value2 = $sourceRange.Value2
            }
        }
        else {
            $dataSheet.Cells.Item(1, $feedCol).Value2 = "Channel Name"
            $headerMap.Remove("Feed Name")
            $headerMap["Channel Name"] = $feedCol
        }
    }

    foreach ($requiredHeader in @("Channel Name", "Pdate", "Brand Name", "Aaddur", "Category", "Company")) {
        if (-not $headerMap.ContainsKey($requiredHeader)) {
            throw "Required column missing from CSV: $requiredHeader"
        }
    }

    $lastRow = $usedRange.Rows.Count
    $lastCol = $usedRange.Columns.Count

    $pdateRange = $dataSheet.Range($dataSheet.Cells.Item(2, $headerMap["Pdate"]), $dataSheet.Cells.Item($lastRow, $headerMap["Pdate"]))
    $pdateRange.TextToColumns(
        $pdateRange,
        1,
        1,
        1,
        $false,
        $false,
        $false,
        $false,
        $false,
        $false,
        $false,
        3
    ) | Out-Null
    $pdateRange.NumberFormat = "dd-mmm-yyyy"

    $aaddurRange = $dataSheet.Range($dataSheet.Cells.Item(2, $headerMap["Aaddur"]), $dataSheet.Cells.Item($lastRow, $headerMap["Aaddur"]))
    $aaddurRange.NumberFormat = "0"
    $aaddurRange.Value2 = $aaddurRange.Value2

    $listsSheet.Range("A1").Value2 = "Excluded Categories"
    for ($i = 0; $i -lt $excludedCategories.Count; $i++) {
        $listsSheet.Cells.Item($i + 2, 1).Value2 = $excludedCategories[$i]
    }
    $listsSheet.Range("B1").Value2 = "Top N Options"
    $listsSheet.Range("B2").Value2 = "Top 10"
    $listsSheet.Range("B3").Value2 = "Top 20"
    $listsSheet.Columns("A:B").AutoFit() | Out-Null

    $dataSheet.Cells.Item(1, $lastCol + 1).Value2 = "IncludeFlag"
    $includeFormula = '=IF(COUNTIF(Lists!$A$2:$A$9,[@Category])>0,"Exclude","Include")'
    $dataRange = $dataSheet.Range($dataSheet.Cells.Item(1, 1), $dataSheet.Cells.Item($lastRow, $lastCol + 1))
    $table = $dataSheet.ListObjects.Add($xlDatabase, $dataRange, $null, $xlYes)
    $table.Name = "tblCTV"
    $table.TableStyle = "TableStyleMedium2"
    $table.ListColumns.Item("IncludeFlag").DataBodyRange.Formula = $includeFormula
    $dataSheet.Columns.AutoFit() | Out-Null

    [void]$workbook.Names.Add("rngExcludedCategories", "=Lists!`$A`$2:`$A`$9")
    [void]$workbook.Names.Add("rngTopNOptions", "=Lists!`$B`$2:`$B`$3")
    [void]$workbook.Names.Add("selTopN", '=VALUE(RIGHT(Dashboard!$Q$4,2))')
    [void]$workbook.Names.Add("rngTopNames", '=OFFSET(Dashboard!$B$11,0,0,selTopN,1)')
    [void]$workbook.Names.Add("rngTopValues", '=OFFSET(Dashboard!$C$11,0,0,selTopN,1)')

    $pivotCache = $workbook.PivotCaches().Create($xlSourceTypeDatabase, "tblCTV", $xlPivotTableVersion15)

    $pivotTop = $pivotCache.CreatePivotTable($pivotSheet.Range("A3"), "ptTopProducts")
    $pivotTop.ManualUpdate = $true
    $pivotTop.PivotFields("IncludeFlag").Orientation = $xlPageField
    $pivotTop.PivotFields("IncludeFlag").CurrentPage = "Include"
    $pivotTop.PivotFields("Brand Name").Orientation = $xlRowField
    [void]$pivotTop.AddDataField($pivotTop.PivotFields("Aaddur"), "Sum of AADDUR", $xlSum)
    $pivotTop.RowAxisLayout($xlTabularRow)
    $pivotTop.PivotFields("Brand Name").AutoSort($xlDescending, "Sum of AADDUR")
    $pivotTop.DataFields(1).NumberFormat = "#,##0"
    $pivotTop.ManualUpdate = $false

    $pivotKpi = $pivotCache.CreatePivotTable($pivotSheet.Range("F3"), "ptKPI")
    $pivotKpi.ManualUpdate = $true
    $pivotKpi.PivotFields("IncludeFlag").Orientation = $xlPageField
    $pivotKpi.PivotFields("IncludeFlag").CurrentPage = "Include"
    [void]$pivotKpi.AddDataField($pivotKpi.PivotFields("Aaddur"), "Total AADDUR", $xlSum)
    [void]$pivotKpi.AddDataField($pivotKpi.PivotFields("Channel Name"), "Total Channels", $xlCount)
    [void]$pivotKpi.AddDataField($pivotKpi.PivotFields("Brand Name"), "Total Brands", $xlCount)
    [void]$pivotKpi.AddDataField($pivotKpi.PivotFields("Company"), "Total Companies", $xlCount)
    [void]$pivotKpi.AddDataField($pivotKpi.PivotFields("Brand Name"), "Total Records", $xlCount)
    $pivotKpi.DataFields(1).NumberFormat = "#,##0"
    $pivotKpi.ManualUpdate = $false

    $pivotProductChannel = $pivotCache.CreatePivotTable($pivotChannelSheet.Range("A3"), "ptProductChannel")
    $pivotProductChannel.ManualUpdate = $true
    $pivotProductChannel.PivotFields("IncludeFlag").Orientation = $xlPageField
    $pivotProductChannel.PivotFields("IncludeFlag").CurrentPage = "Include"
    $pivotProductChannel.PivotFields("Brand Name").Orientation = $xlRowField
    $pivotProductChannel.PivotFields("Channel Name").Orientation = $xlColumnField
    [void]$pivotProductChannel.AddDataField($pivotProductChannel.PivotFields("Aaddur"), "Sum of AADDUR", $xlSum)
    $pivotProductChannel.RowAxisLayout($xlTabularRow)
    $pivotProductChannel.PivotFields("Brand Name").AutoSort($xlDescending, "Sum of AADDUR")
    $pivotProductChannel.DataFields(1).NumberFormat = "#,##0"
    $pivotProductChannel.ManualUpdate = $false

    $pivotDateProduct = $pivotCache.CreatePivotTable($pivotDateSheet.Range("A3"), "ptDateProduct")
    $pivotDateProduct.ManualUpdate = $true
    $pivotDateProduct.PivotFields("IncludeFlag").Orientation = $xlPageField
    $pivotDateProduct.PivotFields("IncludeFlag").CurrentPage = "Include"
    $pivotDateProduct.PivotFields("Pdate").Orientation = $xlRowField
    $pivotDateProduct.PivotFields("Brand Name").Orientation = $xlColumnField
    [void]$pivotDateProduct.AddDataField($pivotDateProduct.PivotFields("Aaddur"), "Sum of AADDUR", $xlSum)
    $pivotDateProduct.RowAxisLayout($xlTabularRow)
    $pivotDateProduct.DataFields(1).NumberFormat = "#,##0"
    $pivotDateProduct.ManualUpdate = $false

    $pivotVisibleChannels = $pivotCache.CreatePivotTable($pivotSheet.Range("Z3"), "ptVisibleChannels")
    $pivotVisibleChannels.ManualUpdate = $true
    $pivotVisibleChannels.PivotFields("IncludeFlag").Orientation = $xlPageField
    $pivotVisibleChannels.PivotFields("IncludeFlag").CurrentPage = "Include"
    $pivotVisibleChannels.PivotFields("Channel Name").Orientation = $xlRowField
    [void]$pivotVisibleChannels.AddDataField($pivotVisibleChannels.PivotFields("Aaddur"), "Sum of AADDUR", $xlSum)
    $pivotVisibleChannels.PivotFields("Channel Name").AutoSort($xlDescending, "Sum of AADDUR")
    $pivotVisibleChannels.ManualUpdate = $false

    $pivotVisibleDates = $pivotCache.CreatePivotTable($pivotSheet.Range("Z60"), "ptVisibleDates")
    $pivotVisibleDates.ManualUpdate = $true
    $pivotVisibleDates.PivotFields("IncludeFlag").Orientation = $xlPageField
    $pivotVisibleDates.PivotFields("IncludeFlag").CurrentPage = "Include"
    $pivotVisibleDates.PivotFields("Pdate").Orientation = $xlRowField
    [void]$pivotVisibleDates.AddDataField($pivotVisibleDates.PivotFields("Aaddur"), "Sum of AADDUR", $xlSum)
    $pivotVisibleDates.ManualUpdate = $false

    foreach ($pt in @($pivotTop, $pivotKpi, $pivotProductChannel, $pivotDateProduct, $pivotVisibleChannels, $pivotVisibleDates)) {
        $pt.HasAutoFormat = $false
        $pt.DisplayErrorString = $true
        $pt.ErrorString = ""
        [void]$pt.RefreshTable()
    }

    $dashboardSheet.Cells.Clear()
    $dashboardSheet.Range("A1:U150").Font.Name = "Segoe UI"
    $dashboardSheet.Range("A1:U150").Font.Size = 9
    $dashboardSheet.Range("A1:U150").Interior.Color = 16777215

    $dashboardSheet.Range("A1:H2").Merge()
    $dashboardSheet.Range("A1").Value2 = "CTV FTC Dashboard"
    $dashboardSheet.Range("A1").Font.Size = 20
    $dashboardSheet.Range("A1").Font.Bold = $true
    $dashboardSheet.Range("A1").HorizontalAlignment = -4131

    $dashboardSheet.Range("P3").Value2 = "Top N"
    $dashboardSheet.Range("P3").Font.Bold = $true
    $dashboardSheet.Range("Q4").Value2 = "Top 10"
    $dashboardSheet.Range("Q4").Interior.Color = 15921906
    $dashboardSheet.Range("Q4").Borders.LineStyle = 1
    $dashboardSheet.Range("Q4").HorizontalAlignment = -4108
    $dashboardSheet.Range("Q4").Validation.Delete()
    $dashboardSheet.Range("Q4").Validation.Add(3, 1, 1, "=rngTopNOptions")

    $cardTitles = @(
        @{ LabelCell = "A4"; ValueCell = "A5"; Title = "Total AADDUR"; Formula = '=GETPIVOTDATA("Total AADDUR",Pivots!$F$3)'; Format = "#,##0" },
        @{ LabelCell = "E4"; ValueCell = "E5"; Title = "Total Channels"; Formula = '=GETPIVOTDATA("Total Channels",Pivots!$F$3)'; Format = "0" },
        @{ LabelCell = "I4"; ValueCell = "I5"; Title = "Total Brands"; Formula = '=GETPIVOTDATA("Total Brands",Pivots!$F$3)'; Format = "0" },
        @{ LabelCell = "M4"; ValueCell = "M5"; Title = "Total Companies"; Formula = '=GETPIVOTDATA("Total Companies",Pivots!$F$3)'; Format = "0" },
        @{ LabelCell = "Q6"; ValueCell = "Q7"; Title = "Total Records"; Formula = '=GETPIVOTDATA("Total Records",Pivots!$F$3)'; Format = "0" }
    )

    foreach ($card in $cardTitles) {
        $labelRange = $dashboardSheet.Range($card.LabelCell).Resize(1, 3)
        $valueRange = $dashboardSheet.Range($card.ValueCell).Resize(2, 3)
        $labelRange.Merge()
        $valueRange.Merge()
        $labelRange.Value2 = $card.Title
        $labelRange.Interior.Color = 2105376
        $labelRange.Font.Color = 16777215
        $labelRange.Font.Bold = $true
        $labelRange.HorizontalAlignment = -4108
        $valueRange.Formula = $card.Formula
        $valueRange.NumberFormat = $card.Format
        $valueRange.Font.Bold = $true
        $valueRange.Font.Size = 18
        $valueRange.HorizontalAlignment = -4108
        $valueRange.VerticalAlignment = -4108
        $valueRange.Borders.LineStyle = 1
        $valueRange.Borders.Color = 14540253
        $valueRange.Interior.Color = 15921906
    }

    Set-SectionHeader -Sheet $dashboardSheet -RangeAddress "A10:C10" -Text "Top Products"
    $dashboardSheet.Range("A11:C11").Value2 = @("Rank", "Product Name", "Sum of AADDUR")
    $dashboardSheet.Range("A11:C11").Font.Bold = $true
    $dashboardSheet.Range("A11:C11").Interior.Color = 15921906
    for ($row = 12; $row -le 31; $row++) {
        $n = $row - 11
        $dashboardSheet.Cells.Item($row, 1).Formula = "=IF($n<=selTopN,$n,"""")"
        $dashboardSheet.Cells.Item($row, 2).Formula = "=IF($n<=selTopN,IFERROR(INDEX(Pivots!`$A:`$A,$n+3),""""),"""")"
        $dashboardSheet.Cells.Item($row, 3).Formula = "=IF($n<=selTopN,IFERROR(INDEX(Pivots!`$B:`$B,$n+3),NA()),NA())"
    }
    $dashboardSheet.Range("C12:C31").NumberFormat = "#,##0"
    Format-Grid -Sheet $dashboardSheet -RangeAddress "A11:C31"

    Set-SectionHeader -Sheet $dashboardSheet -RangeAddress "A34:J34" -Text "Top Products vs Channels"
    $dashboardSheet.Range("A35:J35").Font.Bold = $true
    $dashboardSheet.Range("A35").Value2 = "Product"
    for ($col = 2; $col -le 10; $col++) {
        $index = $col - 1
        $dashboardSheet.Cells.Item(35, $col).Formula = "=IFERROR(INDEX(Pivots!`$Z:`$Z,$index+3),"""")"
    }
    for ($row = 36; $row -le 55; $row++) {
        $idx = $row - 35
        $dashboardSheet.Cells.Item($row, 1).Formula = "=IF($idx<=selTopN,IFERROR(INDEX(Pivots!`$A:`$A,$idx+3),""""),"""")"
        for ($col = 2; $col -le 10; $col++) {
            $colLetter = ([char](64 + $col))
            $formula = '=IF(OR($A{0}="",{1}$35=""),NA(),IFERROR(GETPIVOTDATA("Sum of AADDUR",PivotChannel!$A$3,"Brand Name",$A{0},"Channel Name",{1}$35),0))' -f $row, $colLetter
            $dashboardSheet.Cells.Item($row, $col).Formula = $formula
        }
    }
    $dashboardSheet.Range("B36:J55").NumberFormat = "#,##0"
    $dashboardSheet.Range("A35:J35").Interior.Color = 15921906
    Format-Grid -Sheet $dashboardSheet -RangeAddress "A35:J55"

    Set-SectionHeader -Sheet $dashboardSheet -RangeAddress "A58:U58" -Text "Top Products vs Date"
    $dashboardSheet.Range("A59:U59").Font.Bold = $true
    $dashboardSheet.Range("A59").Value2 = "Date"
    for ($col = 2; $col -le 21; $col++) {
        $idx = $col - 1
        $dashboardSheet.Cells.Item(59, $col).Formula = "=IF($idx<=selTopN,IFERROR(INDEX(Pivots!`$A:`$A,$idx+3),""""),"""")"
    }
    for ($row = 60; $row -le 99; $row++) {
        $idx = $row - 59
        $dashboardSheet.Cells.Item($row, 1).Formula = "=IFERROR(INDEX(Pivots!`$Z:`$Z,$idx+60),"""")"
        $dashboardSheet.Cells.Item($row, 1).NumberFormat = "dd-mmm-yyyy"
        for ($col = 2; $col -le 21; $col++) {
            $colLetter = ([char](64 + $col))
            $formula = '=IF(OR($A{0}="",{1}$59=""),NA(),IFERROR(GETPIVOTDATA("Sum of AADDUR",PivotDate!$A$3,"Pdate",$A{0},"Brand Name",{1}$59),0))' -f $row, $colLetter
            $dashboardSheet.Cells.Item($row, $col).Formula = $formula
        }
    }
    $dashboardSheet.Range("B60:U99").NumberFormat = "#,##0"
    $dashboardSheet.Range("A59:U59").Interior.Color = 15921906
    Format-Grid -Sheet $dashboardSheet -RangeAddress "A59:U99"

    Set-SectionHeader -Sheet $dashboardSheet -RangeAddress "A102:C102" -Text "Excluded Categories"
    for ($i = 0; $i -lt $excludedCategories.Count; $i++) {
        $dashboardSheet.Cells.Item($i + 103, 1).Value2 = $excludedCategories[$i]
    }
    Format-Grid -Sheet $dashboardSheet -RangeAddress "A103:A110"

    $topChart = $dashboardSheet.Shapes.AddChart2(201, $xlBarClustered, 360, 230, 600, 260).Chart
    $topChart.SetSourceData($dashboardSheet.Range("B11:C31"))
    $topChart.SeriesCollection(1).XValues = "=Dashboard!rngTopNames"
    $topChart.SeriesCollection(1).Values = "=Dashboard!rngTopValues"
    $topChart.HasTitle = $true
    $topChart.ChartTitle.Text = "Top Products by Sum of AADDUR"
    $topChart.HasLegend = $false
    $topChart.SeriesCollection(1).ApplyDataLabels($xlDataLabelShowValue) | Out-Null
    $topChart.Axes(1).HasTitle = $true
    $topChart.Axes(1).AxisTitle.Text = "Sum of AADDUR"
    $topChart.Axes(2).HasTitle = $true
    $topChart.Axes(2).AxisTitle.Text = "Product Name"
    $topChart.Axes(2).ReversePlotOrder = $true

    $channelChart = $dashboardSheet.Shapes.AddChart2(201, $xlColumnClustered, 800, 780, 620, 280).Chart
    $channelChart.SetSourceData($dashboardSheet.Range("A35:J55"))
    $channelChart.HasTitle = $true
    $channelChart.ChartTitle.Text = "Top Products vs Channels"
    $channelChart.HasLegend = $true
    $channelChart.Axes(1).HasTitle = $true
    $channelChart.Axes(1).AxisTitle.Text = "Product Name"
    $channelChart.Axes(2).HasTitle = $true
    $channelChart.Axes(2).AxisTitle.Text = "Sum of AADDUR"
    try { $channelChart.SeriesCollection(1).ApplyDataLabels($xlDataLabelShowValue) | Out-Null } catch {}

    $dateChart = $dashboardSheet.Shapes.AddChart2(201, $xlLine, 800, 1290, 620, 300).Chart
    $dateChart.SetSourceData($dashboardSheet.Range("A59:U99"))
    $dateChart.HasTitle = $true
    $dateChart.ChartTitle.Text = "Top Products vs Date"
    $dateChart.HasLegend = $true
    $dateChart.Axes(1).HasTitle = $true
    $dateChart.Axes(1).AxisTitle.Text = "Date"
    $dateChart.Axes(2).HasTitle = $true
    $dateChart.Axes(2).AxisTitle.Text = "Sum of AADDUR"

    $slicerCacheChannel = $workbook.SlicerCaches.Add($pivotTop, "Channel Name", "scChannel")
    [void]$slicerCacheChannel.Slicers.Add("Dashboard", $xlMissing, "slChannel", "Channel Name", 980, 20, 180, 180)

    $dateSlicerCache = $workbook.SlicerCaches.Add($pivotTop, "Pdate", "scPdate")
    [void]$dateSlicerCache.Slicers.Add("Dashboard", $xlMissing, "slDate", "Date", 1180, 20, 220, 180)

    foreach ($sc in @($slicerCacheChannel, $dateSlicerCache)) {
        foreach ($pt in @($pivotTop, $pivotKpi, $pivotProductChannel, $pivotDateProduct, $pivotVisibleChannels, $pivotVisibleDates)) {
            try {
                $sc.PivotTables.AddPivotTable($pt)
            } catch {
            }
        }
    }

    $dashboardSheet.Columns("A:U").ColumnWidth = 12
    $dashboardSheet.Columns("B").ColumnWidth = 26
    $dashboardSheet.Columns("A").ColumnWidth = 14
    $dashboardSheet.Columns("Q").ColumnWidth = 12
    $dashboardSheet.Rows("1:120").RowHeight = 21
    $dashboardSheet.Rows("1:2").RowHeight = 26
    $dashboardSheet.Activate()
    $dashboardSheet.Range("A1").Select() | Out-Null

    $listsSheet.Visible = $xlSheetHidden
    $pivotSheet.Visible = $xlSheetHidden
    $pivotChannelSheet.Visible = $xlSheetHidden
    $pivotDateSheet.Visible = $xlSheetHidden

    $workbook.RefreshAll()
    $workbook.SaveAs($OutputPath, 51)
    $workbook.Close($true)
}
finally {
    if ($workbook) { $workbook | Release-ComObject }
    if ($excel) {
        try {
            $excel.Quit()
        } catch {
        }
        $excel | Release-ComObject
    }
    [gc]::Collect()
    [gc]::WaitForPendingFinalizers()
}

#!/usr/bin/env pwsh
<#!
.SYNOPSIS
  Convert CSV/TSV files into SQL INSERT statements.

.DESCRIPTION
  - Table name defaults to the input filename stem (e.g., DOMAIN.csv -> DOMAIN)
  - Column list comes from the header row
  - Values are SQL-escaped and emitted as:
      INSERT INTO <table> (<cols...>) VALUES
        (...),
        (...)
      ;

  Delimiter is auto-detected (comma vs tab, with fallbacks for ';' and '|').

.EXAMPLE
  # Default output: writes DOMAIN.sql next to DOMAIN.csv
  pwsh tools/csv_to_sql_insert.ps1 out-egs/DOMAIN.csv

.EXAMPLE
  pwsh tools/csv_to_sql_insert.ps1 out-egs/*.csv -Output inserts.sql -BatchSize 5000

.EXAMPLE
  # Stream to stdout explicitly
  pwsh tools/csv_to_sql_insert.ps1 out-egs/DOMAIN.csv -Output -

.NOTES
  - Empty fields default to NULL (controlled by -EmptyAsNull)
  - Type inference is OFF by default (enable with -InferTypes)
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
  [string[]] $Inputs,

  [Parameter()]
  [string] $Output,

  [Parameter()]
  [switch] $Force,

  [Parameter()]
  [string] $Table,

  [Parameter()]
  [bool] $QuoteIdentifiers = $true,

  [Parameter()]
  [bool] $EmptyAsNull = $true,

  [Parameter()]
  [switch] $InferTypes,

  [Parameter()]
  [int] $BatchSize = 1000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-UniqueNewPath {
  param([Parameter(Mandatory = $true)][string] $Path)

  if (-not (Test-Path -LiteralPath $Path)) { return $Path }

  $dir = Split-Path -Parent $Path
  $base = [System.IO.Path]::GetFileNameWithoutExtension($Path)
  $ext = [System.IO.Path]::GetExtension($Path)
  if (-not $ext) { $ext = '.sql' }

  for ($i = 1; $i -le 10000; $i++) {
    $candidate = Join-Path $dir ("$base" + "_$i" + $ext)
    if (-not (Test-Path -LiteralPath $candidate)) { return $candidate }
  }

  throw "Unable to choose a new output path for: $Path"
}

function Get-DefaultOutputPath {
  param([Parameter(Mandatory = $true)][string[]] $ResolvedInputPaths)

  if ($ResolvedInputPaths.Count -eq 1) {
    $p = $ResolvedInputPaths[0]
    return [System.IO.Path]::ChangeExtension($p, '.sql')
  }

  return (Join-Path (Get-Location) 'inserts.sql')
}

function Quote-Ident {
  param(
    [Parameter(Mandatory = $true)][string] $Name,
    [Parameter(Mandatory = $true)][bool] $Enabled
  )

  $n = $Name.Trim()
  if (-not $Enabled) { return $n }
  return '"' + ($n -replace '"', '""') + '"'
}

function Try-SqlNumber {
  param([Parameter(Mandatory = $true)][string] $Text)

  if ($Text.Length -eq 0) { return $null }
  if ($Text -ne $Text.Trim()) { return $null }

  $neg = $Text.StartsWith('-')
  $digits = if ($neg) { $Text.Substring(1) } else { $Text }

  # Integer, but avoid coercing IDs like 00123 -> 123
  if ($digits -match '^[0-9]+$') {
    if ($digits.Length -gt 1 -and $digits.StartsWith('0')) { return $null }
    return $Text
  }

  # Float / scientific notation (conservative)
  $allowed = '0123456789+-eE.'.ToCharArray()
  foreach ($ch in $Text.ToCharArray()) {
    if ($allowed -notcontains $ch) { return $null }
  }
  if ($Text -notmatch '[0-9]') { return $null }

  $style = [System.Globalization.NumberStyles]::Float
  $culture = [System.Globalization.CultureInfo]::InvariantCulture
  [double] $parsed = 0
  if (-not [double]::TryParse($Text, $style, $culture, [ref]$parsed)) { return $null }

  if ([double]::IsNaN($parsed) -or [double]::IsInfinity($parsed)) { return $null }

  # Keep the original spelling to avoid rewriting (e.g. 1e-6 -> 0.000001)
  return $Text
}

function Sql-Literal {
  param(
    [AllowNull()][string] $Value,
    [Parameter(Mandatory = $true)][bool] $EmptyAsNull,
    [Parameter(Mandatory = $true)][bool] $InferTypes
  )

  if ($null -eq $Value) { return 'NULL' }
  if ($Value -eq '' -and $EmptyAsNull) { return 'NULL' }

  if ($InferTypes) {
    $num = Try-SqlNumber -Text $Value
    if ($null -ne $num) { return $num }
  }

  $escaped = $Value -replace "'", "''"
  return "'$escaped'"
}

function Get-Delimiter {
  param([Parameter(Mandatory = $true)][string] $Path)

  $candidates = @(",", "`t", ";", "|")
  $maxLines = 20

  $lines = New-Object System.Collections.Generic.List[string]
  $reader = [System.IO.StreamReader]::new($Path, [System.Text.Encoding]::UTF8, $true)
  try {
    while (-not $reader.EndOfStream -and $lines.Count -lt $maxLines) {
      $line = $reader.ReadLine()
      if ($null -ne $line -and $line.Trim().Length -gt 0) {
        $lines.Add($line)
      }
    }
  } finally {
    $reader.Dispose()
  }

  if ($lines.Count -eq 0) { return ',' }

  $best = ','
  $bestScore = -1

  foreach ($d in $candidates) {
    $dc = [char]$d
    $score = 0
    foreach ($l in $lines) {
      # Count occurrences in the line (simple heuristic; parser handles quotes later)
      $score += @($l.ToCharArray() | Where-Object { $_ -eq $dc }).Count
    }
    if ($score -gt $bestScore) {
      $bestScore = $score
      $best = $d
    }
  }

  if ($bestScore -le 0) { return ',' }
  return $best
}

function New-TextFieldParser {
  param(
    [Parameter(Mandatory = $true)][string] $Path,
    [Parameter(Mandatory = $true)][string] $Delimiter
  )

  # TextFieldParser is available in full .NET and PowerShell 7 on most platforms.
  Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction SilentlyContinue | Out-Null
  $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new($Path)
  $parser.TextFieldType = [Microsoft.VisualBasic.FileIO.FieldType]::Delimited
  $parser.SetDelimiters(@($Delimiter))
  $parser.HasFieldsEnclosedInQuotes = $true
  $parser.TrimWhiteSpace = $false
  return $parser
}

function Split-LenientDelimitedLine {
  param(
    [Parameter(Mandatory = $true)][string] $Line,
    [Parameter(Mandatory = $true)][string] $Delimiter
  )

  # Delimiter is a single character in this script (',', tab, ';', '|')
  $dc = [char]$Delimiter
  return $Line.Split(@($dc), [System.StringSplitOptions]::None)
}

function Write-InsertBatch {
  param(
    [Parameter(Mandatory = $true)][System.IO.TextWriter] $Writer,
    [Parameter(Mandatory = $true)][string] $TableName,
    [Parameter(Mandatory = $true)][string[]] $Header,
    [Parameter(Mandatory = $true)][System.Collections.Generic.List[string[]]] $Rows,
    [Parameter(Mandatory = $true)][bool] $QuoteIdentifiers,
    [Parameter(Mandatory = $true)][bool] $EmptyAsNull,
    [Parameter(Mandatory = $true)][bool] $InferTypes
  )

  $qTable = Quote-Ident -Name $TableName -Enabled $QuoteIdentifiers
  $qCols = ($Header | ForEach-Object { Quote-Ident -Name $_ -Enabled $QuoteIdentifiers }) -join ', '

  $Writer.Write("INSERT INTO $qTable ($qCols) VALUES`n")

  for ($i = 0; $i -lt $Rows.Count; $i++) {
    $row = $Rows[$i]
    $vals = @()
    foreach ($v in $row) {
      $vals += (Sql-Literal -Value $v -EmptyAsNull $EmptyAsNull -InferTypes $InferTypes)
    }

    $suffix = if ($i -lt ($Rows.Count - 1)) { ",`n" } else { "`n" }
    $Writer.Write("  (" + ($vals -join ', ') + ")" + $suffix)
  }

  $Writer.Write(";`n")
}

function Write-InsertsForFile {
  param(
    [Parameter(Mandatory = $true)][string] $InputPath,
    [Parameter(Mandatory = $true)][System.IO.TextWriter] $Writer,
    [Parameter()][string] $TableName
  )

  $resolved = (Resolve-Path -LiteralPath $InputPath).Path
  $delim = Get-Delimiter -Path $resolved

  # Avoid Split-Path -LeafBase (not available in older Windows PowerShell)
  $table = if ($TableName) { $TableName } else { [System.IO.Path]::GetFileNameWithoutExtension($resolved) }

  $parser = New-TextFieldParser -Path $resolved -Delimiter $delim
  try {
    if ($parser.EndOfData) { throw "Empty file: $resolved" }

    $header = $parser.ReadFields()
    if ($null -eq $header -or $header.Length -eq 0) { throw "Missing header row: $resolved" }
    $header = $header | ForEach-Object { $_.Trim() }

    $rows = New-Object System.Collections.Generic.List[string[]]

    $lenientCount = 0
    $lenientWarnLimit = 10

    while (-not $parser.EndOfData) {
      $row = $null
      try {
        $row = $parser.ReadFields()
      }
      catch [Microsoft.VisualBasic.FileIO.MalformedLineException] {
        # Some vocab files contain quotes that are not valid CSV/TSV quoting, e.g.:
        #   40316943<TAB>"Call" - postponed<TAB>...
        # TextFieldParser treats this as malformed because the field starts with a quote
        # but has content after the closing quote. Fall back to a simple delimiter split.
        $badLine = $parser.ErrorLine

        # Advance past the bad line.
        $null = $parser.ReadLine()

        if ($null -eq $badLine -or $badLine -eq '') {
          throw
        }

        $row = Split-LenientDelimitedLine -Line $badLine -Delimiter $delim
        $lenientCount++
        if ($lenientCount -le $lenientWarnLimit) {
          Write-Warning "Malformed quoting at line $($parser.ErrorLineNumber) in $resolved; using lenient delimiter split."
        }
        elseif ($lenientCount -eq ($lenientWarnLimit + 1)) {
          Write-Warning "Additional malformed lines encountered in $resolved; suppressing further warnings."
        }
      }

      if ($null -eq $row) { continue }

      if ($row.Length -lt $header.Length) {
        $padded = New-Object string[] $header.Length
        [Array]::Copy($row, $padded, $row.Length)
        for ($k = $row.Length; $k -lt $header.Length; $k++) { $padded[$k] = '' }
        $row = $padded
      }
      elseif ($row.Length -gt $header.Length) {
        throw "Row has $($row.Length) fields but header has $($header.Length) fields in $resolved"
      }

      $rows.Add($row)

      if ($rows.Count -ge $BatchSize) {
        Write-InsertBatch -Writer $Writer -TableName $table -Header $header -Rows $rows `
          -QuoteIdentifiers $QuoteIdentifiers -EmptyAsNull $EmptyAsNull -InferTypes ([bool]$InferTypes)
        $rows.Clear()
      }
    }

    if ($rows.Count -gt 0) {
      Write-InsertBatch -Writer $Writer -TableName $table -Header $header -Rows $rows `
        -QuoteIdentifiers $QuoteIdentifiers -EmptyAsNull $EmptyAsNull -InferTypes ([bool]$InferTypes)
    }
  }
  finally {
    $parser.Close()
  }
}

if ($BatchSize -le 0) { throw "-BatchSize must be > 0" }
if ($Table -and $Inputs.Count -ne 1) { throw "-Table can only be used with a single input file" }

$inputPaths = @()
foreach ($i in $Inputs) {
  # Expand wildcards in a cross-platform way
  $expanded = Get-ChildItem -Path $i -File -ErrorAction SilentlyContinue
  if ($expanded) {
    $inputPaths += $expanded.FullName
  }
  elseif (Test-Path -LiteralPath $i) {
    $inputPaths += (Resolve-Path -LiteralPath $i).Path
  }
  else {
    throw "Input not found: $i"
  }
}

if ($Output -eq '-') {
  $writer = [Console]::Out
  for ($idx = 0; $idx -lt $inputPaths.Count; $idx++) {
    if ($idx -gt 0) { $writer.Write("`n") }
    Write-InsertsForFile -InputPath $inputPaths[$idx] -Writer $writer -TableName $Table
  }
  return
}

$outputPath = if ($Output) { $Output } else { Get-DefaultOutputPath -ResolvedInputPaths $inputPaths }

$parent = Split-Path -Parent $outputPath
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
  New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

if (Test-Path -LiteralPath $outputPath) {
  if ($Force) {
    # ok to overwrite
  }
  elseif ($Output) {
    throw "Output file already exists: $outputPath. Use -Force to overwrite, or choose a different -Output."
  }
  else {
    $outputPath = Get-UniqueNewPath -Path $outputPath
  }
}

$enc = [System.Text.UTF8Encoding]::new($false)
$writer = [System.IO.StreamWriter]::new($outputPath, $false, $enc)
try {
  for ($idx = 0; $idx -lt $inputPaths.Count; $idx++) {
    if ($idx -gt 0) { $writer.Write("`n") }
    Write-InsertsForFile -InputPath $inputPaths[$idx] -Writer $writer -TableName $Table
  }
}
finally {
  $writer.Flush()
  $writer.Dispose()
}

Write-Host "Wrote SQL inserts to: $outputPath"

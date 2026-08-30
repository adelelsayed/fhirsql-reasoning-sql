# Generates the TRAIN population (~15,000 patients) as 8 sub-batches.
# Deliberately varied by age bracket and US state to broaden archetype coverage
# (general / paediatric / geriatric-polypharmacy / oncology-skewed).
# Seed family 10000-10399, disjoint from the held-out seed family (20000-20399) by design.
# Reference date fixed at 20260802 across every batch so age/date-relative logic is
# computed against the same calendar day everywhere.
#
# Each batch writes to its own --exporter.baseDirectory (rather than one shared output
# folder) because bulk_data NDJSON append-vs-overwrite behavior across repeated
# invocations was not confirmed from docs. Batches are merged in a later step.

$jar = "C:\dev\fhirsql\synthea\synthea-with-dependencies.jar"
$outRoot = "C:\dev\fhirsql\synthea\output\train"

$batches = @(
    @{ Name = "general_ma";   Pop = 3000; Age = $null;    State = "Massachusetts";   Seed = 10001 },
    @{ Name = "general_ca";   Pop = 3000; Age = $null;    State = "California";      Seed = 10002 },
    @{ Name = "general_tx";   Pop = 3000; Age = $null;    State = "Texas";           Seed = 10003 },
    @{ Name = "pediatric_oh"; Pop = 1250; Age = "0-17";   State = "Ohio";            Seed = 10101 },
    @{ Name = "pediatric_fl"; Pop = 1250; Age = "0-17";   State = "Florida";         Seed = 10102 },
    @{ Name = "geriatric_pa"; Pop = 1250; Age = "65-100"; State = "Pennsylvania";    Seed = 10201 },
    @{ Name = "geriatric_il"; Pop = 1250; Age = "65-100"; State = "Illinois";        Seed = 10202 },
    @{ Name = "oncology_ny";  Pop = 1000; Age = "45-89";  State = "New York";        Seed = 10301 }
)

foreach ($b in $batches) {
    $outDir = Join-Path $outRoot $b.Name
    $args = @(
        "-jar", $jar,
        "-p", $b.Pop,
        "-s", $b.Seed,
        "-cs", $b.Seed,
        "-r", "20260802",
        "--exporter.fhir.bulk_data=true",
        "--exporter.baseDirectory=$outDir"
    )
    if ($b.Age) { $args += @("-a", $b.Age) }
    $args += $b.State

    Write-Host "=== TRAIN batch: $($b.Name) ($($b.Pop) patients, seed $($b.Seed)) ===" -ForegroundColor Cyan
    $start = Get-Date
    & java @args
    $elapsed = (Get-Date) - $start
    Write-Host "=== $($b.Name) done in $($elapsed.ToString()) ===" -ForegroundColor Green
}

Write-Host "All TRAIN batches complete." -ForegroundColor Yellow

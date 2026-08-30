# Generates the HELD-OUT population (~5,000 patients) as 5 sub-batches.
# Same rationale as run_train_batches.ps1, but with a disjoint seed family (20000-20399)
# and disjoint states from the train script, so held-out is a genuinely independent
# population, not just a different RNG draw of the same batches.
# Reference date fixed at 20260802, matching the train script.

$jar = "C:\dev\fhirsql\synthea\synthea-with-dependencies.jar"
$outRoot = "C:\dev\fhirsql\synthea\output\heldout"

$batches = @(
    @{ Name = "general_wa";   Pop = 1500; Age = $null;    State = "Washington";      Seed = 20001 },
    @{ Name = "general_ga";   Pop = 1500; Age = $null;    State = "Georgia";         Seed = 20002 },
    @{ Name = "pediatric_nc"; Pop = 800;  Age = "0-17";   State = "North Carolina";  Seed = 20101 },
    @{ Name = "geriatric_az"; Pop = 800;  Age = "65-100"; State = "Arizona";         Seed = 20201 },
    @{ Name = "oncology_co";  Pop = 400;  Age = "45-89";  State = "Colorado";        Seed = 20301 }
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

    Write-Host "=== HELDOUT batch: $($b.Name) ($($b.Pop) patients, seed $($b.Seed)) ===" -ForegroundColor Cyan
    $start = Get-Date
    & java @args
    $elapsed = (Get-Date) - $start
    Write-Host "=== $($b.Name) done in $($elapsed.ToString()) ===" -ForegroundColor Green
}

Write-Host "All HELDOUT batches complete." -ForegroundColor Yellow

namespace AppointmentIntegration.Api.Services;
public sealed class PharmacyImageService(IWebHostEnvironment environment)
{
    public const int MaxBytes = 5 * 1024 * 1024;
    public async Task<string> UploadAsync(IFormFile file, CancellationToken token)
    {
        if (file.Length is <= 0 or > MaxBytes) throw new ArgumentException("Choose a photograph up to 5 MB.");
        var extension = Path.GetExtension(file.FileName).ToLowerInvariant();
        if (extension == ".jpeg") extension = ".jpg";
        if (extension is not (".jpg" or ".png" or ".webp")) throw new ArgumentException("Choose a JPEG, PNG or WebP photograph.");
        await using var input = file.OpenReadStream();
        using var bytes = new MemoryStream();
        var buffer = new byte[81920];
        int read;
        while ((read = await input.ReadAsync(buffer, token)) > 0) {
            if (bytes.Length + read > MaxBytes) throw new ArgumentException("Choose a photograph up to 5 MB.");
            await bytes.WriteAsync(buffer.AsMemory(0, read), token);
        }
        var data = bytes.ToArray();
        var valid = extension switch {
            ".jpg" => data.Length >= 3 && data[0] == 0xff && data[1] == 0xd8 && data[2] == 0xff,
            ".png" => data.Length >= 8 && data.AsSpan(0, 8).SequenceEqual(new byte[] {137,80,78,71,13,10,26,10}),
            ".webp" => data.Length >= 12 && System.Text.Encoding.ASCII.GetString(data, 0, 4) == "RIFF" && System.Text.Encoding.ASCII.GetString(data, 8, 4) == "WEBP",
            _ => false
        };
        if (!valid) throw new ArgumentException("The file does not match the selected image format.");
        var directory = Path.Combine(environment.ContentRootPath, "wwwroot", "uploads", "pharmacy-information");
        Directory.CreateDirectory(directory);
        var name = Guid.NewGuid().ToString("N") + extension;
        var outputPath = Path.Combine(directory, name);
        try { await File.WriteAllBytesAsync(outputPath, data, token); }
        catch { if (File.Exists(outputPath)) File.Delete(outputPath); throw; }
        return "/uploads/pharmacy-information/" + name;
    }
}

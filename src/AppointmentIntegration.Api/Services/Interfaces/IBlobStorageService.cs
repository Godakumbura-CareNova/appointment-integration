namespace AppointmentIntegration.Api.Services.Interfaces;

public interface IBlobStorageService
{
    Task<BlobUploadResult> UploadReceiptAsync(
        Stream stream,
        string originalFileName,
        string contentType,
        CancellationToken cancellationToken = default);

    Task DeleteAsync(
        string blobName,
        CancellationToken cancellationToken = default);
}

public class BlobUploadResult
{
    public string BlobName { get; set; } = string.Empty;

    public string ContainerName { get; set; } = string.Empty;
}
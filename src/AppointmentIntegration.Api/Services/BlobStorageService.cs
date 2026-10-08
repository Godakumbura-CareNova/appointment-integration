using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
using AppointmentIntegration.Api.Services.Interfaces;
using ReceiptBlobDownloadResult =
    AppointmentIntegration.Api.Services.Interfaces.BlobDownloadResult;

namespace AppointmentIntegration.Api.Services;

public class BlobStorageService : IBlobStorageService
{
    private readonly string? _connectionString;
    private readonly string _containerName;

    public BlobStorageService(IConfiguration configuration)
    {
        _connectionString =
            configuration["AzureBlobStorage:ConnectionString"];

        _containerName =
            configuration["AzureBlobStorage:ReceiptContainer"]
            ?? "appointment-receipts";
    }

    public async Task<ReceiptBlobDownloadResult> DownloadReceiptAsync(
        string blobName,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(blobName))
        {
            throw new ArgumentException(
                "A valid receipt blob name is required.");
        }

        var containerClient =
            GetContainerClient();

        var blobClient =
            containerClient.GetBlobClient(blobName);

        var response =
            await blobClient.DownloadStreamingAsync(
                cancellationToken: cancellationToken);

        return new ReceiptBlobDownloadResult
        {
            Content = response.Value.Content,
            ContentType =
                response.Value.Details.ContentType
                ?? "application/octet-stream"
        };
    }

    public async Task<BlobUploadResult> UploadReceiptAsync(
        Stream stream,
        string originalFileName,
        string contentType,
        CancellationToken cancellationToken = default)
    {
        var containerClient =
            GetContainerClient();

        await containerClient.CreateIfNotExistsAsync(
            PublicAccessType.None,
            cancellationToken: cancellationToken);

        var extension =
            Path.GetExtension(originalFileName);

        var blobName =
            $"appointment-receipts/{DateTime.UtcNow:yyyy/MM}/{Guid.NewGuid():N}{extension}";

        var blobClient =
            containerClient.GetBlobClient(blobName);

        var uploadOptions =
            new BlobUploadOptions
            {
                HttpHeaders =
                    new BlobHttpHeaders
                    {
                        ContentType = contentType
                    }
            };

        await blobClient.UploadAsync(
            stream,
            uploadOptions,
            cancellationToken);

        return new BlobUploadResult
        {
            BlobName = blobName,
            ContainerName = _containerName
        };
    }

    public async Task DeleteAsync(
        string blobName,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(blobName))
        {
            return;
        }

        var containerClient =
            GetContainerClient();

        var blobClient =
            containerClient.GetBlobClient(blobName);

        await blobClient.DeleteIfExistsAsync(
            cancellationToken: cancellationToken);
    }

    private BlobContainerClient GetContainerClient()
    {
        if (string.IsNullOrWhiteSpace(_connectionString))
        {
            throw new InvalidOperationException(
                "Azure Blob Storage is not configured. Receipt upload is unavailable in this environment.");
        }

        var serviceClient =
            new BlobServiceClient(_connectionString);

        return serviceClient.GetBlobContainerClient(
            _containerName);
    }
}